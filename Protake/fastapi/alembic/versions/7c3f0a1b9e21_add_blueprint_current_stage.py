"""add blueprint current_stage

Revision ID: 7c3f0a1b9e21
Revises: 2e7861a9ff17
Create Date: 2026-07-29 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7c3f0a1b9e21'
down_revision: Union[str, None] = '2e7861a9ff17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('blueprints', sa.Column('current_stage', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('blueprints', 'current_stage')
