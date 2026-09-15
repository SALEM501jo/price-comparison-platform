"""
The scrape worker.

    python -m app.services.worker           # drain the queue and exit
    python -m app.services.worker --loop    # stay up, polling

`--loop` is what production runs (deploy/docker-compose.yml): it picks up an
admin's manual trigger within seconds, and with SCRAPE_INTERVAL_HOURS set it
also queues a full scrape by itself on that interval -- see
jobs.enqueue_if_due for why the schedule lives here and not in a cron.
Drain-and-exit stays the default because a process that finishes is easier to
run by hand and to reason about in a script; it never schedules anything.

Either way the work happens OUTSIDE the web process, so a slow scrape never
holds a request worker. It does not make a scrape survive a deploy: the worker
is rebuilt from the same image and recreated by `up -d --build`. What survives
is the JOB. On SIGTERM -- which Docker sends before killing -- the worker puts
the job it was running back in the queue and exits, so the next worker starts
it again at once instead of the row sitting in `running` until
jobs.reclaim_stale gives up on it an hour later. A run restarted that way
begins again from the first store.
"""

from __future__ import annotations

import argparse
import logging
import signal
import time

from app.config import get_settings
from app.database import SessionLocal
from app.logging_config import setup_logging
from app.services import jobs

logger = logging.getLogger("app.scraper")
settings = get_settings()

POLL_SECONDS = 10


def schedule(interval_hours: int) -> bool:
    """Queue a scheduled full scrape if one is due. Returns whether it did."""
    if interval_hours <= 0:
        return False
    db = SessionLocal()
    try:
        return jobs.enqueue_if_due(db, interval_hours) is not None
    finally:
        db.close()


def tick(interval_hours: int) -> int:
    """
    One pass of the loop: schedule if due, then run whatever is queued.

    Scheduling FIRST, in the same pass, so a due run starts now rather than
    one poll later -- and a separate function so the loop's behaviour can be
    tested without an infinite loop.
    """
    schedule(interval_hours)
    return drain()


def drain() -> int:
    """Run every queued job. Returns how many were processed."""
    db = SessionLocal()
    processed = 0
    try:
        # Before claiming anything, return jobs abandoned by a killed process.
        # A deploy during a run leaves one stuck in `running` forever.
        jobs.reclaim_stale(db)

        while True:
            job = jobs.claim_next(db)
            if job is None:
                return processed
            logger.info(
                "Worker claimed a scrape job",
                extra={
                    "action": "scrape_job_claimed",
                    "target": job.store_codes or "all stores",
                    "success": True,
                },
            )
            # run_job records its own failure on the row; one bad job must
            # not stop the ones behind it.
            try:
                jobs.run_job(db, job)
            except (KeyboardInterrupt, SystemExit):
                # Being stopped (SIGTERM from a deploy, or Ctrl+C). Hand the
                # job back before going. On a FRESH session: this one may be
                # half way through a transaction the interrupt cut short.
                job_id = job.id
                try:
                    db.rollback()
                except Exception:
                    pass
                fresh = SessionLocal()
                try:
                    jobs.requeue(fresh, job_id)
                finally:
                    fresh.close()
                raise
            processed += 1
    finally:
        db.close()


def _stop(signum, frame) -> None:
    raise SystemExit(0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run queued scrape jobs.")
    parser.add_argument(
        "--loop",
        action="store_true",
        help="Stay up and poll instead of exiting when the queue is empty.",
    )
    parser.add_argument(
        "--poll",
        type=int,
        default=POLL_SECONDS,
        help=f"Seconds between polls with --loop (default {POLL_SECONDS}).",
    )
    args = parser.parse_args()

    setup_logging()

    # Docker stops a container with SIGTERM, then SIGKILL ten seconds later.
    # This process is PID 1 in its container, and the kernel does not apply
    # default signal actions to PID 1 -- without a handler SIGTERM is simply
    # ignored, every deploy waits the full ten seconds, and the kill lands
    # with no chance to requeue. Turning it into SystemExit lets drain() hand
    # the job back on the way out.
    signal.signal(signal.SIGTERM, _stop)

    if not args.loop:
        count = drain()
        print(f"processed {count} job(s)")
        return

    interval = settings.scrape_interval_hours
    logger.info(
        "Scrape worker started",
        extra={
            "action": "worker_start",
            "target": f"scheduled every {interval}h" if interval > 0 else "schedule off",
        },
    )
    while True:
        try:
            tick(interval)
        except Exception:
            # A worker that exits on an unexpected error stops draining the
            # queue entirely. Log it and keep polling.
            logger.error(
                "Worker loop error", exc_info=True, extra={"action": "worker_error"}
            )
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
