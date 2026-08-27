"""
Queued scrape work.

WHY A TABLE AND NOT BackgroundTasks:
BackgroundTasks runs the job inside the web process. A restart kills it
mid-flight, and because nothing recorded that the job existed, nobody finds
out -- the admin saw "started", the deploy happened, and the scrape simply
never finished. It also cannot spread across replicas: with two web machines,
whichever one served the request does all the work while the other idles.

A row survives the restart. The job is enqueued by the request and claimed by
a worker, so the work outlives the process that asked for it, and its history
is visible afterwards instead of living only in a log line.

Postgres has no queue primitive here beyond the row itself, and that is on
purpose: this is a handful of jobs a day, and Celery or RQ would add a broker,
a dependency and a second thing to deploy to solve a problem the database
already solves.
"""

import enum

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func

from app.database import Base


class JobStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    succeeded = "succeeded"
    failed = "failed"


# Stored as text, not a database enum: adding a value to a PostgreSQL enum
# needs ALTER TYPE and cannot be reversed without rewriting the column.
class ScrapeJob(Base):
    __tablename__ = "scrape_jobs"

    id = Column(Integer, primary_key=True, index=True)
    status = Column(
        String(16), nullable=False, default=JobStatus.queued.value, index=True
    )

    # Empty means every store. A comma-separated list rather than a join
    # table: a job names store CODES from the registry, which are
    # configuration, not rows anybody can reference.
    store_codes = Column(String(255), nullable=False, default="")

    # Null when the scheduled runner enqueued it rather than a person.
    requested_by = Column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), index=True
    )

    created_at = Column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    started_at = Column(DateTime(timezone=True))
    finished_at = Column(DateTime(timezone=True))

    # What happened, for the admin screen. Free text so the shape of a run
    # summary can change without a migration.
    result = Column(Text)
    error = Column(Text)

    @property
    def is_finished(self) -> bool:
        return self.status in (JobStatus.succeeded.value, JobStatus.failed.value)
