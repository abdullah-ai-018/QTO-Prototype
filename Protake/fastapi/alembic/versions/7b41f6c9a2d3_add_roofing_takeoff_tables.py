"""add_roofing_takeoff_tables

Revision ID: 7b41f6c9a2d3
Revises: f0c25d97a8e1
Create Date: 2026-08-14 20:10:00.000000

Hand-written, same convention as the drywall/painting/flooring takeoff
migrations: `status`/`roof_feature` are plain VARCHAR, not native enum
columns — `create_type=False` on `sa.Enum` does NOT suppress the
CREATE TYPE statement in Alembic's offline (`--sql`) rendering (verified
directly), so it would collide with the already-existing `rooffeature`
native enum type (created by 4fe9b0d9cb65) the same way a bare `sa.Enum`
would. Plain VARCHAR sidesteps it entirely, matching how
walls.roof_feature and roof_planes.source/status already do this.

These tables are the takeoff snapshot/evidence layer only — separate
from app.models.roof's existing geometry tables (roofs/roof_planes/
roof_edges/roof_openings/roof_penetrations/roof_flashing), which are
untouched by this migration.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '7b41f6c9a2d3'
down_revision: Union[str, None] = 'f0c25d97a8e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'roofing_takeoffs',
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
        'roofing_items',
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
        sa.ForeignKeyConstraint(['takeoff_id'], ['roofing_takeoffs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'roofing_classifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('wall_id', sa.Integer(), nullable=False),
        sa.Column('roof_feature', sa.String(length=10), nullable=True),
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
    op.drop_table('roofing_classifications')
    op.drop_table('roofing_items')
    op.drop_table('roofing_takeoffs')
