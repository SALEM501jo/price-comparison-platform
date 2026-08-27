"""listing condition and used-phone details

Revision ID: d7b2e4915c88
Revises: c3f1a20b7d54
Create Date: 2026-08-27 00:00:00.000000

Condition and the details that only matter for a second-hand unit: battery
health, damage, warranty.

WHY ON product_aliases AND NOT ON products:
A `Product` is a model -- "iPhone 15 128GB Black". A `ProductAlias` is one
shop's actual unit of it. Battery health, a scratched corner and a photo of
that scratch describe the unit, not the model, so putting them on the product
would make one shop's worn handset describe every other shop's listing of the
same phone.

`condition` is a plain String rather than a PostgreSQL enum. Adding a value to
an enum needs ALTER TYPE and cannot be undone without rewriting the column
(see the merchant migration), and `match_method` on this same table already
stores a small vocabulary as text.

Everything already in the catalogue is scraped from a retailer's own feed, so
it is new by definition and backfilled that way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d7b2e4915c88"
down_revision: Union[str, None] = "c3f1a20b7d54"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_aliases",
        sa.Column(
            "condition",
            sa.String(length=16),
            nullable=False,
            server_default="new",
        ),
    )
    # Indexed because every product page and every search now groups by it.
    op.create_index(
        "ix_product_aliases_condition", "product_aliases", ["condition"]
    )

    # Null for a new unit -- "unknown" and "100%" are different claims, and a
    # sealed phone makes neither.
    op.add_column(
        "product_aliases", sa.Column("battery_health", sa.Integer(), nullable=True)
    )
    op.add_column(
        "product_aliases", sa.Column("has_damage", sa.Boolean(), nullable=True)
    )
    op.add_column(
        "product_aliases",
        sa.Column("damage_notes", sa.String(length=500), nullable=True),
    )
    op.add_column(
        "product_aliases", sa.Column("warranty_months", sa.Integer(), nullable=True)
    )
    op.add_column(
        "product_aliases",
        sa.Column("listing_notes", sa.String(length=1000), nullable=True),
    )

    # The server_default did the backfill; drop it so the application layer
    # stays the single place that decides what a new listing means.
    op.alter_column("product_aliases", "condition", server_default=None)


def downgrade() -> None:
    op.drop_column("product_aliases", "listing_notes")
    op.drop_column("product_aliases", "warranty_months")
    op.drop_column("product_aliases", "damage_notes")
    op.drop_column("product_aliases", "has_damage")
    op.drop_column("product_aliases", "battery_health")
    op.drop_index("ix_product_aliases_condition", table_name="product_aliases")
    op.drop_column("product_aliases", "condition")
