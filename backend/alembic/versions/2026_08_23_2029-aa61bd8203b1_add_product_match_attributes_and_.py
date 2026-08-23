"""add product match attributes and uniqueness constraints

Adds the structured matching data used by app/matching/, and promotes three
invariants that were previously only enforced in Python into database
constraints.

The constraint operations use batch_alter_table so this migration runs on
SQLite as well as Postgres. SQLite cannot ALTER TABLE ... ADD CONSTRAINT, so
Alembic's batch mode rebuilds the table with a copy-and-move; on Postgres it
emits a plain ALTER. Without this the migration could not be exercised at all
outside a live Postgres server.

Revision ID: aa61bd8203b1
Revises: 38293ce69b5c
Create Date: 2026-08-23 20:29:15.084601

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'aa61bd8203b1'
down_revision: Union[str, None] = '38293ce69b5c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Structured matching data -----------------------------------------
    op.add_column(
        "products", sa.Column("match_category", sa.String(length=50), nullable=True)
    )
    op.add_column("products", sa.Column("match_attributes", sa.JSON(), nullable=True))
    op.create_index(
        op.f("ix_products_match_category"), "products", ["match_category"], unique=False
    )
    op.create_index(
        "ix_products_match_category_brand",
        "products",
        ["match_category", "brand"],
        unique=False,
    )

    # --- Invariants that used to live only in Python ----------------------

    # The scraper inserted a duplicate alias on every run; the Python guard is
    # the fast path, this makes the violation impossible.
    with op.batch_alter_table("product_aliases") as batch_op:
        batch_op.create_unique_constraint(
            "uq_alias_store_sku", ["store_id", "store_product_id"]
        )

    # "prices" holds the CURRENT price only; history lives in price_history.
    with op.batch_alter_table("prices") as batch_op:
        batch_op.create_unique_constraint("uq_price_current_per_alias", ["alias_id"])

    # The router checks for an existing row first, but two concurrent requests
    # can both pass that check and insert.
    with op.batch_alter_table("wishlist_items") as batch_op:
        batch_op.create_unique_constraint(
            "uq_wishlist_user_product", ["user_id", "product_id"]
        )


def downgrade() -> None:
    with op.batch_alter_table("wishlist_items") as batch_op:
        batch_op.drop_constraint("uq_wishlist_user_product", type_="unique")

    with op.batch_alter_table("prices") as batch_op:
        batch_op.drop_constraint("uq_price_current_per_alias", type_="unique")

    with op.batch_alter_table("product_aliases") as batch_op:
        batch_op.drop_constraint("uq_alias_store_sku", type_="unique")

    op.drop_index("ix_products_match_category_brand", table_name="products")
    op.drop_index(op.f("ix_products_match_category"), table_name="products")
    op.drop_column("products", "match_attributes")
    op.drop_column("products", "match_category")
