"""
The scrape queue: enqueue, claim, run.

THE ONLY INTERESTING PART IS THE CLAIM. Two workers polling the same table
will both see the same queued row, and without care both will run it -- which
means two scrapes hitting a store's servers at once, from a system whose whole
scraping stance is to be polite.

The claim is therefore a CONDITIONAL UPDATE, not a read followed by a write:

    UPDATE scrape_jobs SET status='running' WHERE id=? AND status='queued'

The database decides. Exactly one worker's UPDATE matches a row; every other
gets rowcount 0 and moves on. This is portable -- no SELECT FOR UPDATE SKIP
LOCKED, which would tie the queue to PostgreSQL and leave the SQLite test
suite exercising a different code path from production.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, Sequence

from sqlalchemy import update
from sqlalchemy.orm import Session

from app.models.scrape_job import JobStatus, ScrapeJob

logger = logging.getLogger("app.scraper")

# A job left running longer than this is presumed dead -- the process was
# killed mid-flight. Generous: a full run of every store is minutes of
# deliberately spaced-out requests.
STALE_AFTER_MINUTES = 60


def enqueue(
    db: Session,
    store_codes: Sequence[str] = (),
    requested_by: Optional[int] = None,
) -> ScrapeJob:
    """Queue a run. Returns immediately; a worker picks it up."""
    job = ScrapeJob(
        status=JobStatus.queued.value,
        store_codes=",".join(store_codes),
        requested_by=requested_by,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    logger.info(
        "Scrape job queued",
        extra={
            "action": "scrape_job_queued",
            "target": job.store_codes or "all stores",
            "user_id": requested_by,
            "success": True,
        },
    )
    return job


def claim_next(db: Session) -> Optional[ScrapeJob]:
    """
    Take the oldest queued job, or None.

    The UPDATE is the lock. Reading a row and then marking it running would
    let two workers both read it as queued and both proceed -- the classic
    lost-update race, which here means two scrapes of the same store at once.
    """
    while True:
        candidate = (
            db.query(ScrapeJob)
            .filter(ScrapeJob.status == JobStatus.queued.value)
            .order_by(ScrapeJob.created_at, ScrapeJob.id)
            .first()
        )
        if candidate is None:
            return None

        result = db.execute(
            update(ScrapeJob)
            .where(
                ScrapeJob.id == candidate.id,
                # The guard. Without it this is a plain write and the race
                # is wide open.
                ScrapeJob.status == JobStatus.queued.value,
            )
            .values(
                status=JobStatus.running.value,
                started_at=datetime.now(timezone.utc),
            )
        )
        db.commit()

        if result.rowcount == 1:
            db.refresh(candidate)
            return candidate
        # Another worker won it. Look for the next one rather than giving up.


def finish(db: Session, job: ScrapeJob, result: str) -> None:
    job.status = JobStatus.succeeded.value
    job.result = result
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    logger.info(
        "Scrape job finished",
        extra={"action": "scrape_job_finished", "target": result, "success": True},
    )


def fail(db: Session, job: ScrapeJob, error: str) -> None:
    """
    Record the failure on the ROW, not only in the log.

    A job that died silently is the thing this queue exists to prevent: the
    admin screen has to be able to say "this run failed, here is why" without
    anyone reading server logs.
    """
    job.status = JobStatus.failed.value
    job.error = error[:4000]
    job.finished_at = datetime.now(timezone.utc)
    db.commit()
    logger.error(
        "Scrape job failed",
        extra={"action": "scrape_job_failed", "target": error[:200], "success": False},
    )


def reclaim_stale(db: Session) -> int:
    """
    Return jobs abandoned by a dead process to the queue.

    Without this a job killed mid-run sits in `running` forever, and every
    later worker walks past it. Deploys kill processes routinely, so this is
    the normal case rather than the exceptional one.
    """
    cutoff = datetime.now(timezone.utc).timestamp() - STALE_AFTER_MINUTES * 60
    stale = [
        job
        for job in db.query(ScrapeJob)
        .filter(ScrapeJob.status == JobStatus.running.value)
        .all()
        if job.started_at
        and (
            job.started_at.replace(tzinfo=timezone.utc)
            if job.started_at.tzinfo is None
            else job.started_at
        ).timestamp()
        < cutoff
    ]
    for job in stale:
        job.status = JobStatus.queued.value
        job.started_at = None
    if stale:
        db.commit()
        logger.warning(
            "Requeued abandoned scrape jobs",
            extra={
                "action": "scrape_job_reclaimed",
                "target": str(len(stale)),
                "success": True,
            },
        )
    return len(stale)


def run_job(db: Session, job: ScrapeJob) -> None:
    """Execute one claimed job, recording the outcome either way."""
    # Imported here rather than at module scope: ingest pulls in the scrapers,
    # which pull in httpx, and the queue is imported by the web process on
    # every request path that touches admin.
    from app.services.ingest import IngestService
    from app.services.scrapers import STORES, store_by_code

    codes = [c for c in (job.store_codes or "").split(",") if c]
    targets = [store_by_code(c) for c in codes] if codes else list(STORES)
    targets = [t for t in targets if t]

    try:
        service = IngestService(db)
        outcomes = [service.run_store(config) for config in targets]
        finish(db, job, "; ".join(str(o) for o in outcomes) or "nothing to do")
    except Exception as exc:  # noqa: BLE001 - recorded, then re-raised to the caller
        db.rollback()
        fail(db, job, f"{type(exc).__name__}: {exc}")
