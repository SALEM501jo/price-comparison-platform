"""prices.checked_at: when a scraper last re-read the price

Revision ID: 9b4c2f7e1d63
Revises: 7d3b9e21c5a8
Create Date: 2026-09-15 13:00:00.000000

The first scheduled scrape on production confirmed hundreds of prices
unchanged, and the product page went on saying "updated 19 days ago" beside
every one of them. last_updated only moves when a column changes, and it
should keep meaning "the price changed": the sitemap's lastmod and the
merchant staleness warning are built on that. So the read gets its own column.

NULLABLE AND NOT BACKFILLED. Copying last_updated in would claim every row
was checked at the moment it last changed, which is not known, and would
stamp merchant prices -- which nothing re-reads -- with a check that never
happened. A null means "not re-read since this column existed"; the page falls
back to last_updated, exactly what it showed before, until the next scrape
(within six hours) fills it in.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "9b4c2f7e1d63"
down_revision: Union[str, None] = "7d3b9e21c5a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("prices", sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("prices", "checked_at")
