"""contact events

Revision ID: a3d7c419b62f
Revises: f4a91c2d5e08
Create Date: 2026-08-28 09:00:00.000000

Records a shopper tapping Call, WhatsApp or Facebook on a shop's listing.

There is no checkout on this platform -- the transaction happens on the phone
-- so a shop currently has no way to see what the site did for it. A merchant
asked to pay a monthly fee will ask "how many customers did you send me?", and
this table is the answer.

It counts TAPS, not calls: whether the number was rung, answered, or led to a
sale is outside what a web page can see, and reporting taps as calls would
inflate the one number a merchant is billed against.

NO PERSONAL DATA. A row is (shop, product, channel, when). No IP, no user id,
no session key, so this cannot become a record of what any individual browsed
-- which also means duplicate taps by one person cannot be collapsed. Counting
unique people would require identifying people; taps is the honest unit.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "a3d7c419b62f"
down_revision: Union[str, None] = "f4a91c2d5e08"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "contact_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("store_id", sa.Integer(), nullable=False),
        # Nullable: the tap is still real if the product row is later merged
        # or cleaned up, and dropping it would quietly reduce a billed number.
        sa.Column("product_id", sa.Integer(), nullable=True),
        # Text, not a database enum -- the project's standing decision, so a
        # new channel does not need ALTER TYPE.
        sa.Column("channel", sa.String(length=16), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["products.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_contact_events_id"), "contact_events", ["id"], unique=False
    )
    op.create_index(
        op.f("ix_contact_events_store_id"), "contact_events", ["store_id"]
    )
    op.create_index(
        op.f("ix_contact_events_product_id"), "contact_events", ["product_id"]
    )
    op.create_index(
        op.f("ix_contact_events_channel"), "contact_events", ["channel"]
    )
    op.create_index(
        op.f("ix_contact_events_created_at"), "contact_events", ["created_at"]
    )
    # The index that actually serves the queries: every question is "this
    # shop, over this period", from both the merchant dashboard and the admin
    # screen. store_id alone still leaves every row that shop ever collected.
    op.create_index(
        "ix_contact_events_store_created",
        "contact_events",
        ["store_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_contact_events_store_created", table_name="contact_events")
    op.drop_index(op.f("ix_contact_events_created_at"), table_name="contact_events")
    op.drop_index(op.f("ix_contact_events_channel"), table_name="contact_events")
    op.drop_index(op.f("ix_contact_events_product_id"), table_name="contact_events")
    op.drop_index(op.f("ix_contact_events_store_id"), table_name="contact_events")
    op.drop_index(op.f("ix_contact_events_id"), table_name="contact_events")
    op.drop_table("contact_events")
