"""add schedule_items table

Revision ID: bfe655115620
Revises: d6b0a468a8dd
Create Date: 2026-07-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bfe655115620'
down_revision: Union[str, None] = 'd6b0a468a8dd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'schedule_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('schedule_type', sa.Enum('ROOM', 'WALL', 'DOOR', 'WINDOW', 'COLUMN', 'SYMBOL', 'OBJECT', name='detectionkind'), nullable=False),
        sa.Column('item_code', sa.String(length=50), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('attributes', sa.JSON(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'APPROVED', 'REJECTED', name='reviewstatus'), nullable=False),
        sa.Column('reviewed_by_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['reviewed_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('schedule_items')
