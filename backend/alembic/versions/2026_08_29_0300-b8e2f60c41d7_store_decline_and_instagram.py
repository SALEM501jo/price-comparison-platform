"""store decline and instagram

Revision ID: b8e2f60c41d7
Revises: a3d7c419b62f
Create Date: 2026-08-29 03:00:00.000000

Two columns on stores.

rejected_at gives merchant review a third state. With only is_verified there
was no way to say NO: a fake claim stayed in the pending queue forever,
indistinguishable from one nobody had looked at yet, so the queue could not be
cleared and an admin re-read the same bad claim on every visit. A timestamp
rather than a flag, for the same reason email_verified_at is one -- "when"
answers questions a boolean cannot. Cleared on approval, so a decline is
reversible and a shop that later sends proof is approved rather than stuck.

instagram_url is where a lot of small Jordanian phone shops actually keep
their shopfront, frequently instead of a Facebook page rather than as well as
one. A shop with only an Instagram previously had nowhere to put it.

Both are nullable with no backfill: every existing row is correct as NULL --
no claim has been declined, and no shop has told us an Instagram.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "b8e2f60c41d7"
down_revision: Union[str, None] = "a3d7c419b62f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "stores", sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column(
        "stores", sa.Column("instagram_url", sa.String(length=500), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("stores", "instagram_url")
    op.drop_column("stores", "rejected_at")
