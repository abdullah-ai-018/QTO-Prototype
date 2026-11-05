"""add pages.discipline/primary_title/classification_confidence/geometry_authority

The page classifier already computes discipline, primary_title, a
confidence score, and a geometry_authority label for every page (see
app.geometry.page_classifier.ClassificationResult / classify_page_content),
but only page_type/is_takeoff_eligible/skip_reason previously made it onto
the Page row — the rest was computed and discarded, forcing the frontend
to re-derive a cruder discipline/confidence guess of its own from sheet
code/title string matching. This persists the real values.

Nullable, no server_default: existing rows predate this classification
data and must read as "not classified" (null), not a fabricated default.

Revision ID: a1b2c3d4e5f6
Revises: e1a2b3c4d5e6
Create Date: 2026-08-26 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'e1a2b3c4d5e6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("pages", sa.Column("discipline", sa.String(length=30), nullable=True))
    op.add_column("pages", sa.Column("primary_title", sa.String(length=255), nullable=True))
    op.add_column("pages", sa.Column("classification_confidence", sa.Float(), nullable=True))
    op.add_column("pages", sa.Column("geometry_authority", sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column("pages", "geometry_authority")
    op.drop_column("pages", "classification_confidence")
    op.drop_column("pages", "primary_title")
    op.drop_column("pages", "discipline")
