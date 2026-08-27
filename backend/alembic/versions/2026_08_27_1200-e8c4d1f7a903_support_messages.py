"""support messages from the contact form

Revision ID: e8c4d1f7a903
Revises: d7b2e4915c88
Create Date: 2026-08-27 12:00:00.000000

Contact-form messages are stored rather than only emailed. Mail is the least
reliable link here -- the console backend discards it in development and SMTP
fails in production -- and a support request that vanishes is worse than one
never sent, because its author is waiting for an answer.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8c4d1f7a903"
down_revision: Union[str, None] = "d7b2e4915c88"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "support_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("subject", sa.String(length=150), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.Column(
            "handled", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        # SET NULL, not CASCADE: deleting an account must not erase the
        # support history that may explain why it was deleted.
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_support_messages_id", "support_messages", ["id"])
    op.create_index("ix_support_messages_email", "support_messages", ["email"])
    op.create_index("ix_support_messages_user_id", "support_messages", ["user_id"])
    op.create_index("ix_support_messages_handled", "support_messages", ["handled"])
    op.create_index(
        "ix_support_messages_created_at", "support_messages", ["created_at"]
    )


def downgrade() -> None:
    op.drop_table("support_messages")
