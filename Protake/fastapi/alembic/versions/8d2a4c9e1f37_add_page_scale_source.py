"""add_page_scale_source

Revision ID: 8d2a4c9e1f37
Revises: 4fe9b0d9cb65
Create Date: 2026-08-13 00:00:00.000000

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '8d2a4c9e1f37'
down_revision: Union[str, None] = '4fe9b0d9cb65'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('pages', sa.Column('scale_source', sa.String(length=30), nullable=True))


def downgrade() -> None:
    op.drop_column('pages', 'scale_source')
