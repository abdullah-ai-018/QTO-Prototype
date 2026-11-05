"""add_wall_face_provenance_columns

Revision ID: e1a2b3c4d5e6
Revises: c4a71f3d8e92
Create Date: 2026-08-21 00:00:00.000000

Persists the dual-face provenance (face_a_segment_id, face_b_segment_id,
face_a_coords, face_b_coords, overlap_ratio) that the geometry engine
computes in memory but previously discarded when the Wall row was
committed.  Without these columns every wall reloaded from the DB falls
into the PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE tier (because
has_independent_faces is False) regardless of how clean the PDF geometry
was — the dual-face confirmation is simply lost at persistence time.

Engineering reason: The 5-state decision machine in drywall_semantic.py
rewards PHYSICAL_WALL_CONFIRMED (dual independent faces) with
confidence=0.95 and qto_eligible=True when assembly is verified.
PHYSICAL_WALL_CONFIRMED_SINGLE_SOURCE gets confidence=0.85 at best.
When every wall loaded from DB falls into single-source, the QTO gate
opens with systematically lower confidence than the geometry warranted.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e1a2b3c4d5e6"
down_revision = "a4f8c1d92b6e"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("walls", schema=None) as batch_op:
        batch_op.add_column(sa.Column("face_a_segment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("face_b_segment_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("face_a_coords", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("face_b_coords", sa.JSON(), nullable=True))
        batch_op.add_column(sa.Column("overlap_ratio", sa.Float(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("walls", schema=None) as batch_op:
        batch_op.drop_column("overlap_ratio")
        batch_op.drop_column("face_b_coords")
        batch_op.drop_column("face_a_coords")
        batch_op.drop_column("face_b_segment_id")
        batch_op.drop_column("face_a_segment_id")
