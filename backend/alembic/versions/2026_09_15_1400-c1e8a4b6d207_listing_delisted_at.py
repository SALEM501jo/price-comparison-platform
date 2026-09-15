"""product_aliases.delisted_at: the store no longer lists this

Revision ID: c1e8a4b6d207
Revises: 9b4c2f7e1d63
Create Date: 2026-09-15 14:00:00.000000

The scheduled scrape re-reads every store, but a listing the store has
removed simply stops appearing -- and nothing noticed. Its last price stayed
in every comparison, could win "best price", and its link led to the store's
404 page. Live on 2026-09-15: iPhone 16 128GB at SmartBuy, 689 JOD, marked
best price, while https://smartbuy-me.com/products/abj1501st0307 returned
404 Not Found.

A timestamp, not a flag, so the admin can see WHEN a listing went, and so a
listing that comes back (a product briefly unpublished) is re-listed by
clearing it. Indexed: every shopper-facing price query filters on it.

NOT BACKFILLED. Which rows are gone today is only known after a complete read
of each store's feed, which the next scheduled run performs; guessing from
timestamps here would hide listings that are merely beyond the old per-store
cap and still on sale.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c1e8a4b6d207"
down_revision: Union[str, None] = "9b4c2f7e1d63"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_aliases",
        sa.Column("delisted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_product_aliases_delisted_at", "product_aliases", ["delisted_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_product_aliases_delisted_at", table_name="product_aliases")
    op.drop_column("product_aliases", "delisted_at")
