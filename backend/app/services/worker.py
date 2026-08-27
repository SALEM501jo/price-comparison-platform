"""
The scrape worker.

    python -m app.services.worker           # drain the queue and exit
    python -m app.services.worker --loop    # stay up, polling

DRAIN-AND-EXIT IS THE DEFAULT because that is what the scheduled runner wants:
GitHub Actions already runs this repository's code on a cron, and a process
that finishes is far easier to reason about in CI than one that must be
killed. `--loop` is for a deployment that keeps a worker machine running so an
admin's manual trigger is picked up within seconds rather than at the next
cron tick.

Either way the work happens OUTSIDE the web process, which is the entire
point: a deploy no longer kills a scrape in flight, and the job survives to be
retried.
"""

from __future__ import annotations

import argparse
import logging
import time

from app.database import SessionLocal
from app.logging_config import setup_logging
from app.services import jobs

logger = logging.getLogger("app.scraper")

POLL_SECONDS = 10


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
            jobs.run_job(db, job)
            processed += 1
    finally:
        db.close()


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

    if not args.loop:
        count = drain()
        print(f"processed {count} job(s)")
        return

    logger.info("Scrape worker started", extra={"action": "worker_start"})
    while True:
        try:
            drain()
        except Exception:
            # A worker that exits on an unexpected error stops draining the
            # queue entirely. Log it and keep polling.
            logger.error(
                "Worker loop error", exc_info=True, extra={"action": "worker_error"}
            )
        time.sleep(args.poll)


if __name__ == "__main__":
    main()
