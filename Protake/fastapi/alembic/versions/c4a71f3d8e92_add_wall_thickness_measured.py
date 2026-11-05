"""add walls.thickness_measured

Records whether a wall's thickness_ft was measured off the drawing's own
wall stroke or is the assumed stud-wall default, so the UI can label the
difference rather than presenting an assumption as a measurement.

Revision ID: c4a71f3d8e92
Revises: 9a1c2d3e4f5b
Create Date: 2026-08-03 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c4a71f3d8e92'
down_revision: Union[str, None] = '9a1c2d3e4f5b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # server_default false so existing rows — whose thickness_ft is the old
    # hardcoded 0.42 default, never a measurement — are correctly marked as
    # unmeasured rather than silently claiming to be measured.
    op.add_column(
        "walls",
        sa.Column("thickness_measured", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("walls", "thickness_measured")
