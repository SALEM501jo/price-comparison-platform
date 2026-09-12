"""oauth identities, and a password that may be absent

Revision ID: 4a1e9c07b3d2
Revises: ee543f078cff
Create Date: 2026-09-08 10:30:00.000000

Social sign-in ("Continue with Google", "Sign in with Apple") needs two schema
changes, and they must land together.

oauth_identities records which provider account belongs to which local user,
keyed on the provider's SUBJECT claim rather than the email address. Addresses
change hands -- a corporate mailbox outlives its owner, and an Apple private
relay stops resolving the moment the user unlinks the app -- so the address is
used once, at link time, to prove both sides control the same mailbox, and is
never an identifier afterwards. The foreign key CASCADES so that deleting an
account takes its provider links with it without the deletion code needing to
know this table exists.

users.password_hash becomes NULLABLE because an account created through a
provider has never had a password, and because linking a provider to a
previously UNVERIFIED local account deliberately clears the one it had -- that
password was chosen by somebody who never proved they own the mailbox, and
leaving it in place is the account-takeover path.

WITHOUT THIS MIGRATION the models alone would look fine: the test suite builds
its schema from the models, so it would stay green, while Postgres still
carries the NOT NULL from the initial schema. The insert would raise
IntegrityError, which the global handler turns into 409 "Resource conflict. It
may already exist." -- which reads as "that email is taken" and sends whoever
debugs it in exactly the wrong direction.

THE DOWNGRADE IS LOSSY AND SAYS SO. By the time it runs, accounts exist with
no password at all, and NOT NULL cannot be restored without putting something
in those rows. It writes one random bcrypt hash whose plaintext is generated
here and discarded, so the rows survive and remain NOT NULL, but nobody -- not
even the operator running the downgrade -- can log into them with a password.
Those users recover through the ordinary forgot-password flow, which is gated
on the same mailbox the provider vouched for. The alternative, deleting the
rows, would take their wishlists and price alerts with them.
"""
import secrets
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.security.password import hash_password

revision: str = "4a1e9c07b3d2"
down_revision: Union[str, None] = "ee543f078cff"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "oauth_identities",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("provider_subject", sa.String(length=255), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=True,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        # The PAIR, not the subject alone. Nothing guarantees Google's
        # identifier space is disjoint from Apple's, and unique here is what
        # stops one provider account being bound to two local users.
        sa.UniqueConstraint(
            "provider", "provider_subject", name="uq_oauth_identity_provider_subject"
        ),
    )
    op.create_index(op.f("ix_oauth_identities_id"), "oauth_identities", ["id"])
    op.create_index(
        op.f("ix_oauth_identities_user_id"), "oauth_identities", ["user_id"]
    )

    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=True,
    )


def downgrade() -> None:
    # See the module docstring: this cannot restore what it overwrites.
    placeholder = hash_password(secrets.token_urlsafe(48))
    op.execute(
        sa.text("UPDATE users SET password_hash = :h WHERE password_hash IS NULL")
        .bindparams(h=placeholder)
    )
    op.alter_column(
        "users",
        "password_hash",
        existing_type=sa.String(length=255),
        nullable=False,
    )

    op.drop_index(op.f("ix_oauth_identities_user_id"), table_name="oauth_identities")
    op.drop_index(op.f("ix_oauth_identities_id"), table_name="oauth_identities")
    op.drop_table("oauth_identities")
