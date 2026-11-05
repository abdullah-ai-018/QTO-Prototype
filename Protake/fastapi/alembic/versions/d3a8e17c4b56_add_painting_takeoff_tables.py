"""add_painting_takeoff_tables

Revision ID: d3a8e17c4b56
Revises: ce6da41d52d1
Create Date: 2026-08-14 19:05:00.000000

Hand-written, same convention as ce6da41d52d1 (drywall): `status`/`source`
are plain VARCHAR, not native Postgres enum columns, since both enum
types (TradeTakeoffStatus, DetectionSource) already exist by this point
in the chain — a native CREATE TYPE here would collide.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'd3a8e17c4b56'
down_revision: Union[str, None] = 'ce6da41d52d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'painting_takeoffs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('blueprint_id', sa.Integer(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=True),
        sa.Column('material_quantity', sa.Float(), nullable=False),
        sa.Column('material_unit', sa.String(length=30), nullable=False),
        sa.Column('labor_hours', sa.Float(), nullable=False),
        sa.Column('material_cost', sa.Float(), nullable=False),
        sa.Column('labor_cost', sa.Float(), nullable=False),
        sa.Column('direct_cost', sa.Float(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('evidence', sa.JSON(), nullable=True),
        sa.Column('validation_reasons', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['blueprint_id'], ['blueprints.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['created_by_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'painting_items',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('takeoff_id', sa.Integer(), nullable=False),
        sa.Column('label', sa.String(length=255), nullable=False),
        sa.Column('quantity', sa.Float(), nullable=False),
        sa.Column('unit', sa.String(length=30), nullable=False),
        sa.Column('unit_cost', sa.Float(), nullable=False),
        sa.Column('total_cost', sa.Float(), nullable=False),
        sa.Column('source_proof', sa.JSON(), nullable=True),
        sa.Column('formula_breakdown', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['takeoff_id'], ['painting_takeoffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'painting_classifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wall_id', sa.Integer(), nullable=False),
        sa.Column('paintable', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(length=8), nullable=False),
        sa.Column('reason', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['wall_id'], ['walls.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('wall_id'),
    )


def downgrade() -> None:
    op.drop_table('painting_classifications')
    op.drop_table('painting_items')
    op.drop_table('painting_takeoffs')
