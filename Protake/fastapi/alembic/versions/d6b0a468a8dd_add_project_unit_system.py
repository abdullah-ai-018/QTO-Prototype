"""add project unit_system

Revision ID: d6b0a468a8dd
Revises: 085b02739e4b
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd6b0a468a8dd'
down_revision: Union[str, None] = '085b02739e4b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'projects',
        sa.Column(
            'unit_system',
            sa.Enum('IMPERIAL', 'METRIC', name='unitsystem'),
            nullable=False,
            server_default='IMPERIAL',
        ),
    )


def downgrade() -> None:
    op.drop_column('projects', 'unit_system')
