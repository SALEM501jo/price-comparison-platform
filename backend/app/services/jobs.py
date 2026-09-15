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
from datetime import datetime, timedelta, timezone
from typing import Optional, Sequence

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
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


def _aware(moment: datetime) -> datetime:
    """SQLite hands timestamps back without a zone; they were written as UTC."""
    return moment if moment.tzinfo else moment.replace(tzinfo=timezone.utc)


def enqueue_if_due(
    db: Session, interval_hours: int, now: Optional[datetime] = None
) -> Optional[ScrapeJob]:
    """
    Queue a full scrape if the last one was at least `interval_hours` ago.

    WHY THE WORKER SCHEDULES ITSELF, rather than a cron entry on the server or
    a GitHub Actions cron: a host crontab lives outside the repository, where
    nobody reviewing the code can see it and a rebuilt server silently loses
    it; and a cron in GitHub would have to reach production Postgres, which
    the firewall rightly does not expose. The worker is already running,
    already has the database, and already survives deploys.

    THE CLOCK IS THE LAST FULL RUN OF ANY ORIGIN. An admin pressing "scrape
    all" resets it, so the stores are not fetched twice in quick succession;
    a one-store run does not, because the other stores are still stale.
    Measured from when the run was QUEUED, so a failed run is not retried
    every poll -- a store that is down gets asked again next interval, not
    every ten seconds.

    Nothing is queued while any job is queued or running: a scheduled run
    stacked behind a manual one would fetch every store twice in a row.

    TWO WORKERS AT ONCE. Both can pass the checks above before either inserts.
    The database settles it: a partial unique index allows one full run
    queued or running (migration 7d3b9e21c5a8), so the second INSERT fails and
    that worker simply queues nothing. An earlier check-after-insert did not
    hold on PostgreSQL, where ids are handed out before commit.
    """
    if interval_hours <= 0:
        return None
    now = now or datetime.now(timezone.utc)
    pending = (JobStatus.queued.value, JobStatus.running.value)

    if db.query(ScrapeJob.id).filter(ScrapeJob.status.in_(pending)).first():
        return None

    last_full = (
        db.query(ScrapeJob)
        .filter(ScrapeJob.store_codes == "")
        .order_by(ScrapeJob.created_at.desc(), ScrapeJob.id.desc())
        .first()
    )
    if (
        last_full is not None
        and last_full.created_at is not None
        and _aware(last_full.created_at) > now - timedelta(hours=interval_hours)
    ):
        return None

    try:
        return enqueue(db)
    except IntegrityError:
        # Another worker queued the full run first. Nothing to do.
        db.rollback()
        return None


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


def requeue(db: Session, job_id: int) -> bool:
    """
    Put a job this process was running back in the queue, now.

    For a worker that is being stopped: it knows the job is abandoned, so
    there is no reason to leave the row `running` for reclaim_stale to find an
    hour later -- an hour in which the schedule, which will not queue behind a
    running job, would scrape nothing. Conditional on `running`, like the
    claim: a job that already finished must not be run again.
    """
    result = db.execute(
        update(ScrapeJob)
        .where(ScrapeJob.id == job_id, ScrapeJob.status == JobStatus.running.value)
        .values(status=JobStatus.queued.value, started_at=None)
    )
    db.commit()
    if result.rowcount:
        logger.warning(
            "Requeued a scrape job interrupted by shutdown",
            extra={"action": "scrape_job_requeued", "target": str(job_id), "success": True},
        )
    return bool(result.rowcount)


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
    """
    Execute one claimed job, recording the outcome either way.

    ONE STORE FAILING NO LONGER FAILS THE RUN. This used to run the stores in
    one expression, so a single store that was down or had changed its feed
    raised out of the loop, marked the whole job failed, and skipped every
    store after it -- tolerable for an admin watching a manual run, not for a
    schedule nobody is watching. Each store is now its own attempt; the job
    records which failed and why, and is only `failed` if every store did.

    AFTER THE PRICES, THE CONSEQUENCES, whatever started the run:
      * the catalogue version, always, so search, browse, deals and the
        sitemap stop serving the pre-scrape prices from cache.
      * price alerts, only when every store refreshed (see below).
        process_alerts() used to run only in the GitHub scheduled scrape, so
        once that was gone no alert could fire from a scrape at all. It is
        idempotent -- notified_at stops a second email until the price
        recovers.
    """
    # Imported here rather than at module scope: ingest pulls in the scrapers,
    # which pull in httpx, and the queue is imported by the web process on
    # every request path that touches admin.
    from app.services.cache import bump_catalogue_version_sync
    from app.services.ingest import IngestService
    from app.services.notifications import process_alerts
    from app.services.scrapers import STORES, store_by_code

    codes = [c for c in (job.store_codes or "").split(",") if c]
    targets = [store_by_code(c) for c in codes] if codes else list(STORES)
    targets = [t for t in targets if t]

    service = IngestService(db)
    outcomes: list[str] = []
    failures: list[str] = []
    for config in targets:
        try:
            outcome = service.run_store(config)
        except Exception as exc:  # noqa: BLE001 - recorded on the row below
            db.rollback()
            failures.append(f"{config.name}: {type(exc).__name__}: {exc}")
            logger.error(
                "Store failed during a scrape job",
                exc_info=True,
                extra={
                    "action": "scrape_store_failed",
                    "target": config.name,
                    "success": False,
                },
            )
            continue
        # NOTHING SEEN IS A FAILURE TOO. The scraper does not raise on a 403,
        # a 429, a robots refusal or a feed that stopped being JSON -- it stops
        # and yields nothing, which is the polite thing to do. Counted as a
        # success, a store blocking the bot would read "succeeded" on every
        # run while its prices silently aged. No store on the registry has an
        # empty catalogue.
        if not outcome.get("seen"):
            failures.append(f"{config.name}: returned no listings")
        outcomes.append(str(outcome))

    # Cached pages are retired whatever happened: listings are committed one
    # at a time, so even a store that failed on a later page may already
    # have changed prices.
    if targets:
        bump_catalogue_version_sync()

    if targets and len(failures) == len(targets):
        fail(db, job, "; ".join(failures))
        return

    # ALERTS ONLY AFTER A CLEAN RUN. Alerts judge the cheapest offer across
    # every store, and a store that failed this run still has its old prices
    # in that comparison -- after a long gap, weeks old. Emailing "the price
    # has dropped" on a figure nobody re-checked is the wrong message to send
    # under this name. A store that keeps failing therefore holds alerts back
    # until it is fixed or removed, and the job row says so on every run.
    if failures:
        outcomes.append("alerts skipped: a store failed this run")
    else:
        try:
            outcomes.append(f"alerts: {process_alerts(db)}")
        except Exception as exc:  # noqa: BLE001 - the prices are in; say what did not happen
            db.rollback()
            failures.append(f"alerts: {type(exc).__name__}: {exc}")

    summary = outcomes + [f"FAILED {failure}" for failure in failures]
    finish(db, job, "; ".join(summary) or "nothing to do")
