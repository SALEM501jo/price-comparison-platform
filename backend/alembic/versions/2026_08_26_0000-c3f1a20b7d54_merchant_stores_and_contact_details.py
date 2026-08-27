"""merchant stores, contact details and verification

Revision ID: c3f1a20b7d54
Revises: f1a267fad86f
Create Date: 2026-08-26 00:00:00.000000

Adds the merchant side of the platform: a store can now be owned by a user
who submits its prices, reached by phone rather than by checkout, and hidden
from shoppers until an admin verifies the claim.

Existing stores are backfilled as verified. They are scraped from their own
public feeds, so there is no claim to check -- and leaving them unverified
would empty the catalogue the moment this migration ran.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c3f1a20b7d54"
down_revision: Union[str, None] = "f1a267fad86f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # A new value on an existing PostgreSQL enum. ALTER TYPE ... ADD VALUE is
    # transactional from PostgreSQL 12 onward, which every supported version
    # here satisfies. IF NOT EXISTS keeps the migration re-runnable against a
    # database where a previous attempt got this far and then failed.
    op.execute("ALTER TYPE userrole ADD VALUE IF NOT EXISTS 'merchant'")

    op.add_column("stores", sa.Column("owner_user_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_stores_owner_user_id",
        "stores",
        "users",
        ["owner_user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    # Unique, not merely indexed: one account owns at most one store, and that
    # is a property of the data rather than a rule the endpoint remembers.
    op.create_index(
        "ix_stores_owner_user_id", "stores", ["owner_user_id"], unique=True
    )

    op.add_column("stores", sa.Column("phone", sa.String(length=32), nullable=True))
    op.add_column("stores", sa.Column("whatsapp", sa.String(length=32), nullable=True))
    op.add_column(
        "stores", sa.Column("facebook_url", sa.String(length=500), nullable=True)
    )
    op.add_column(
        "stores",
        sa.Column(
            "is_verified", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
    )
    op.add_column(
        "stores", sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "stores",
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
    )

    # Backfill: everything that exists today is scraped or seeded, so it is
    # verified by definition. Done before the server_default is dropped so
    # new rows still default to unverified.
    op.execute("UPDATE stores SET is_verified = true, verified_at = now()")
    op.alter_column("stores", "is_verified", server_default=None)


def downgrade() -> None:
    op.drop_column("stores", "created_at")
    op.drop_column("stores", "verified_at")
    op.drop_column("stores", "is_verified")
    op.drop_column("stores", "facebook_url")
    op.drop_column("stores", "whatsapp")
    op.drop_column("stores", "phone")
    op.drop_index("ix_stores_owner_user_id", table_name="stores")
    op.drop_constraint("fk_stores_owner_user_id", "stores", type_="foreignkey")
    op.drop_column("stores", "owner_user_id")

    # The 'merchant' enum value is deliberately NOT removed. PostgreSQL has no
    # ALTER TYPE ... DROP VALUE, so undoing it means recreating the type and
    # rewriting every column that uses it. A spare value on an enum is inert;
    # a half-rewritten users table is not. Any account holding the role must
    # be moved off it before downgrading, or the enum cast will fail.
    op.execute("UPDATE users SET role = 'user' WHERE role = 'merchant'")
