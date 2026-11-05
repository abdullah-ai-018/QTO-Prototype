"""add_roofing_models

Revision ID: 4fe9b0d9cb65
Revises: c4a71f3d8e92
Create Date: 2026-08-05 20:30:17.561664

"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = '4fe9b0d9cb65'
down_revision: Union[str, None] = 'c4a71f3d8e92'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums are created automatically by SQLAlchemy when tables are created
    
    # Create roofs table
    op.create_table('roofs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_type', sa.String(), nullable=False),
        sa.Column('material_type', sa.String(), nullable=False),
        sa.Column('complexity', sa.String(), nullable=False),
        sa.Column('total_flat_area_sqft', sa.Float(), nullable=False),
        sa.Column('total_sloped_area_sqft', sa.Float(), nullable=False),
        sa.Column('total_squares', sa.Float(), nullable=False),
        sa.Column('total_perimeter_ft', sa.Float(), nullable=False),
        sa.Column('eave_length_ft', sa.Float(), nullable=False),
        sa.Column('rake_length_ft', sa.Float(), nullable=False),
        sa.Column('ridge_length_ft', sa.Float(), nullable=False),
        sa.Column('hip_length_ft', sa.Float(), nullable=False),
        sa.Column('valley_length_ft', sa.Float(), nullable=False),
        sa.Column('stories', sa.Integer(), nullable=False),
        sa.Column('roof_height_ft', sa.Float(), nullable=False),
        sa.Column('overhang_ft', sa.Float(), nullable=False),
        sa.Column('is_steep_roof', sa.Boolean(), nullable=False),
        sa.Column('requires_crane', sa.Boolean(), nullable=False),
        sa.Column('requires_safety_harness', sa.Boolean(), nullable=False),
        sa.Column('waste_factor_pct', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create roof_planes table
    op.create_table('roof_planes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_id', sa.Integer(), nullable=False),
        sa.Column('plane_name', sa.String(length=100), nullable=False),
        sa.Column('plane_number', sa.Integer(), nullable=False),
        sa.Column('polygon_norm', sa.JSON(), nullable=False),
        sa.Column('centroid_norm', sa.JSON(), nullable=False),
        sa.Column('length_ft', sa.Float(), nullable=False),
        sa.Column('width_ft', sa.Float(), nullable=False),
        sa.Column('flat_area_sqft', sa.Float(), nullable=False),
        sa.Column('sloped_area_sqft', sa.Float(), nullable=False),
        sa.Column('pitch_rise', sa.Float(), nullable=False),
        sa.Column('pitch_run', sa.Float(), nullable=False),
        sa.Column('pitch_angle_degrees', sa.Float(), nullable=False),
        sa.Column('pitch_factor', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roof_id'], ['roofs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create roof_edges table
    op.create_table('roof_edges',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_id', sa.Integer(), nullable=False),
        sa.Column('plane_id', sa.Integer(), nullable=True),
        sa.Column('edge_type', sa.String(length=50), nullable=False),
        sa.Column('start_norm', sa.JSON(), nullable=False),
        sa.Column('end_norm', sa.JSON(), nullable=False),
        sa.Column('length_ft', sa.Float(), nullable=False),
        sa.Column('linear_ft_required', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['plane_id'], ['roof_planes.id'], ondelete='SET NULL'),
        sa.ForeignKeyConstraint(['roof_id'], ['roofs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create roof_openings table
    op.create_table('roof_openings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_id', sa.Integer(), nullable=False),
        sa.Column('opening_type', sa.String(length=50), nullable=False),
        sa.Column('opening_name', sa.String(length=100), nullable=True),
        sa.Column('polygon_norm', sa.JSON(), nullable=False),
        sa.Column('centroid_norm', sa.JSON(), nullable=False),
        sa.Column('length_ft', sa.Float(), nullable=False),
        sa.Column('width_ft', sa.Float(), nullable=False),
        sa.Column('area_sqft', sa.Float(), nullable=False),
        sa.Column('perimeter_ft', sa.Float(), nullable=False),
        sa.Column('requires_flashing', sa.Boolean(), nullable=False),
        sa.Column('flashing_perimeter_ft', sa.Float(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roof_id'], ['roofs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create roof_penetrations table
    op.create_table('roof_penetrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_id', sa.Integer(), nullable=False),
        sa.Column('penetration_type', sa.String(length=50), nullable=False),
        sa.Column('centroid_norm', sa.JSON(), nullable=False),
        sa.Column('diameter_inches', sa.Float(), nullable=False),
        sa.Column('requires_boot', sa.Boolean(), nullable=False),
        sa.Column('requires_flashing', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roof_id'], ['roofs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )

    # Create roof_flashing table
    op.create_table('roof_flashing',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('page_id', sa.Integer(), nullable=False),
        sa.Column('roof_id', sa.Integer(), nullable=False),
        sa.Column('flashing_type', sa.String(length=50), nullable=False),
        sa.Column('location_description', sa.String(length=200), nullable=True),
        sa.Column('length_ft', sa.Float(), nullable=False),
        sa.Column('width_inches', sa.Float(), nullable=False),
        sa.Column('square_ft_required', sa.Float(), nullable=False),
        sa.Column('linear_ft_required', sa.Float(), nullable=False),
        sa.Column('requires_ice_shield', sa.Boolean(), nullable=False),
        sa.Column('requires_sealant', sa.Boolean(), nullable=False),
        sa.Column('confidence', sa.Float(), nullable=False),
        sa.Column('source', sa.String(), nullable=False),
        sa.Column('status', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['page_id'], ['pages.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['roof_id'], ['roofs.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id')
    )


def downgrade() -> None:
    # Drop tables in correct order (dependencies first)
    op.drop_table('roof_flashing')
    op.drop_table('roof_penetrations')
    op.drop_table('roof_openings')
    op.drop_table('roof_edges')
    op.drop_table('roof_planes')
    op.drop_table('roofs')
    
    # Drop enum types
    sa.Enum(name='flashingtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='roofcomplexity').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='roofmaterialtype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='rooftype').drop(op.get_bind(), checkfirst=True)