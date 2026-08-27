"""scrape job queue

Revision ID: f4a91c2d5e08
Revises: e8c4d1f7a903
Create Date: 2026-08-27 16:00:00.000000

Replaces BackgroundTasks with a durable queue.

BackgroundTasks ran the scrape inside the web process: a restart killed it
mid-flight, nothing recorded that the job had existed, and nobody found out.
It also could not spread across replicas. A row survives the restart, and the
run's history is visible afterwards instead of living only in a log line.

A table rather than Celery or RQ: this is a handful of jobs a day, and a
broker would be a dependency and a second thing to deploy to solve a problem
the database already solves.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "f4a91c2d5e08"
down_revision: Union[str, None] = "e8c4d1f7a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "scrape_jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        # Text, not a database enum: adding a value to a PostgreSQL enum
        # needs ALTER TYPE and cannot be undone without rewriting the column.
        sa.Column(
            "status", sa.String(length=16), nullable=False, server_default="queued"
        ),
        sa.Column(
            "store_codes", sa.String(length=255), nullable=False, server_default=""
        ),
        sa.Column("requested_by", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        # SET NULL: deleting the admin who triggered a run must not erase the
        # record that the run happened.
        sa.ForeignKeyConstraint(["requested_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_scrape_jobs_id", "scrape_jobs", ["id"])
    # The claim query filters on status and orders by created_at; this is the
    # index it walks on every poll.
    op.create_index("ix_scrape_jobs_status", "scrape_jobs", ["status"])
    op.create_index("ix_scrape_jobs_created_at", "scrape_jobs", ["created_at"])
    op.create_index("ix_scrape_jobs_requested_by", "scrape_jobs", ["requested_by"])


def downgrade() -> None:
    op.drop_table("scrape_jobs")
