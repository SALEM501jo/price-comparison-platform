"""drop legacy specs column

Revision ID: c5a71d3e9f04
Revises: b8e2f60c41d7
Create Date: 2026-09-01 15:00:00.000000

products.specs held the OLD regex extractor's output and was superseded by
match_attributes when the structured matching engine landed. Both columns were
written on every ingest with the SAME value, and nothing read specs: the API
exposed both fields, the product page already preferred `attributes`, and the
legacy shape it used to hold ({"storage": "128", "model_year": "15"}) reads as
junk in a UI.

Kept around, it is a trap rather than a spare: two fields that mean the same
thing until the day one of them silently does not, and a reader of the schema
has no way to tell which is authoritative.

The downgrade recreates the column NULL rather than trying to reconstruct its
contents from match_attributes. Those values are only equal for rows written
after the matching engine existed, and inventing history for the older ones
would be worse than admitting the data is gone -- nothing reads it either way.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "c5a71d3e9f04"
down_revision: Union[str, None] = "b8e2f60c41d7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("products", "specs")


def downgrade() -> None:
    op.add_column("products", sa.Column("specs", sa.JSON(), nullable=True))
