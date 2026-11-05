"""add estimate item evidence fields

Revision ID: 430bc44c00a2
Revises: bfe655115620
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '430bc44c00a2'
down_revision: Union[str, None] = 'bfe655115620'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('estimate_items', sa.Column('source_proof', sa.JSON(), nullable=True))
    op.add_column('estimate_items', sa.Column('formula_breakdown', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('estimate_items', 'formula_breakdown')
    op.drop_column('estimate_items', 'source_proof')
