"""add_wall_height_source_and_source_tag

Revision ID: f1a2b3c4d5e7
Revises: e1a2b3c4d5e6
Create Date: 2026-08-31 00:00:00.000000

DEF-01/DEF-10: height_source persists the provenance of each wall's height_ft
(ASSUMED / project_default / RCP / section_callout). NULL means ASSUMED for rows
written before this migration — backward-compatible.

DEF-03: source_tag carries the fine-grained geometry origin string from
GeometryWall.source (e.g. 'cad_vector_entity_unnamed_unconfirmed') that was
previously discarded at DB persist because blueprint_service always passed
DetectionSource.GEOMETRY to the coarser `source` enum column. Both columns are
kept: `source` (DetectionSource enum) for broad pipeline routing, `source_tag`
(String) for audit traceability to the original PDF vector extraction path.
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f1a2b3c4d5e7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("walls", schema=None) as batch_op:
        batch_op.add_column(sa.Column("height_source", sa.String(100), nullable=True))
        batch_op.add_column(sa.Column("source_tag", sa.String(200), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("walls", schema=None) as batch_op:
        batch_op.drop_column("source_tag")
        batch_op.drop_column("height_source")
