"""add detectionkind values: fixture, stairs, annotation

Revision ID: 9a1c2d3e4f5b
Revises: 7c3f0a1b9e21
Create Date: 2026-07-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '9a1c2d3e4f5b'
down_revision: Union[str, None] = '7c3f0a1b9e21'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Postgres requires ALTER TYPE ... ADD VALUE to run outside a transaction
# block (autocommit_block), and a value added this way cannot be used in
# the SAME transaction it was added in on older server versions — fine
# here since this migration only adds the labels, nothing inserts them yet.
_NEW_VALUES = ["FIXTURE", "STAIRS", "ANNOTATION"]


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        return
    with op.get_context().autocommit_block():
        for value in _NEW_VALUES:
            op.execute(f"ALTER TYPE detectionkind ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE. Removing these labels
    # would require rebuilding the enum type (create new type, migrate
    # column, drop old type) — not worth it for a downgrade path that's
    # never actually exercised in this project's workflow.
    pass
