"""at most one full scrape queued or running

Revision ID: 7d3b9e21c5a8
Revises: 4a1e9c07b3d2
Create Date: 2026-09-15 12:00:00.000000

The worker now queues a full scrape of every store by itself
(jobs.enqueue_if_due). Two workers deciding at the same moment could both
insert one, and the check-after-insert that tried to prevent it does not hold
on PostgreSQL: a SERIAL id is handed out at INSERT, not at COMMIT, so under
READ COMMITTED each can re-read, see only its own row as the lowest, and keep
it. Two full scrapes back to back is exactly the load on the stores this
system is built to avoid.

A PARTIAL UNIQUE INDEX makes the database refuse the second one. It covers
only rows with empty store_codes (every store) that are queued or running, so
any number of finished runs and one-store runs are unaffected. Not keyed on
requested_by: an admin's "scrape all" and a scheduled run are the same work,
so one pending full run of either kind blocks the other -- and requested_by
is SET NULL when an admin account is deleted, which must never be the update
that violates an index.

Both engines support partial indexes, so the SQLite test suite exercises the
same rule as production.

BEFORE CREATING IT, any duplicates already pending are resolved, or the
CREATE fails, the one-shot migrate container exits non-zero, and the API --
which waits for migrate -- never starts. The one already RUNNING is kept (a
worker may be mid-scrape on it), otherwise the newest queued one; the rest are
marked failed with a reason, not deleted, so the history still shows they
existed.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "7d3b9e21c5a8"
down_revision: Union[str, None] = "4a1e9c07b3d2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

INDEX = "ux_scrape_jobs_one_pending_full_run"
PREDICATE = "store_codes = '' AND status IN ('queued', 'running')"


def upgrade() -> None:
    op.execute(
        f"""
        UPDATE scrape_jobs
           SET status = 'failed',
               error = 'Superseded: another full run was already pending when '
                       'the one-pending-full-run rule was introduced.',
               finished_at = CURRENT_TIMESTAMP
         WHERE {PREDICATE}
           AND id <> (
                SELECT id FROM scrape_jobs
                 WHERE {PREDICATE}
                 ORDER BY CASE WHEN status = 'running' THEN 0 ELSE 1 END, id DESC
                 LIMIT 1
           )
        """
    )
    op.create_index(
        INDEX,
        "scrape_jobs",
        ["store_codes"],
        unique=True,
        postgresql_where=sa.text(PREDICATE),
        sqlite_where=sa.text(PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(INDEX, table_name="scrape_jobs")
