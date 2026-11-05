"""add_takeoff_snapshot_versioning

Revision ID: 9c2e5a71f4d8
Revises: 7b41f6c9a2d3
Create Date: 2026-08-17 12:00:00.000000

Adds geometry_version, scale_version, engine_version to all four
{trade}_takeoffs tables — nullable, purely additive, no data migration
needed since these are fingerprint columns computed fresh on each new
takeoff going forward. Existing rows (if any) get NULL, which callers
should treat as "no version recorded" rather than "definitely stale."
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '9c2e5a71f4d8'
down_revision: Union[str, None] = '7b41f6c9a2d3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TABLES = ("drywall_takeoffs", "painting_takeoffs", "flooring_takeoffs", "roofing_takeoffs")


def upgrade() -> None:
    for table in TABLES:
        op.add_column(table, sa.Column('geometry_version', sa.String(length=32), nullable=True))
        op.add_column(table, sa.Column('scale_version', sa.String(length=32), nullable=True))
        op.add_column(table, sa.Column('engine_version', sa.String(length=20), nullable=True))


def downgrade() -> None:
    for table in TABLES:
        op.drop_column(table, 'engine_version')
        op.drop_column(table, 'scale_version')
        op.drop_column(table, 'geometry_version')
