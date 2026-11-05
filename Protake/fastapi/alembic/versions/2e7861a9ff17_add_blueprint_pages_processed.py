"""add blueprint pages_processed

Revision ID: 2e7861a9ff17
Revises: 430bc44c00a2
Create Date: 2026-07-28 15:10:41.133822

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e7861a9ff17'
down_revision: Union[str, None] = '430bc44c00a2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'blueprints',
        sa.Column('pages_processed', sa.Integer(), nullable=False, server_default='0'),
    )


def downgrade() -> None:
    op.drop_column('blueprints', 'pages_processed')
