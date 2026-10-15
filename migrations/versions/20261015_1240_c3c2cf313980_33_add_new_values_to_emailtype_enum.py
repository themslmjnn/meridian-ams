"""33_add_new_values_to_emailtype_enum

Revision ID: c3c2cf313980
Revises: a19537e6b590
Create Date: 2026-10-15 12:40:48.560187

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3c2cf313980"
down_revision: str | Sequence[str] | None = "a19537e6b590"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'NEW_LOGIN'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
