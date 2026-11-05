"""add_ground_truth_references

Revision ID: a4f8c1d92b6e
Revises: 9c2e5a71f4d8
Create Date: 2026-08-17 12:30:00.000000

New table only, no data. `trade` is plain VARCHAR (not the native
`tradekey` enum type) — same convention as every other takeoff table
migration in this chain, since `tradekey` already exists (created by the
initial estimate_items migration) and a second CREATE TYPE would collide.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a4f8c1d92b6e'
down_revision: Union[str, None] = '9c2e5a71f4d8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'ground_truth_references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('blueprint_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('trade', sa.String(length=10), nullable=False),
        sa.Column('item_label', sa.String(length=255), nullable=False),
        sa.Column('reference_quantity', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=False),
        sa.Column('source', sa.String(length=100), nullable=False),
        sa.Column('verified_by', sa.String(length=255), nullable=True),
        sa.Column('verified_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['blueprint_id'], ['blueprints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )


def downgrade() -> None:
    op.drop_table('ground_truth_references')
