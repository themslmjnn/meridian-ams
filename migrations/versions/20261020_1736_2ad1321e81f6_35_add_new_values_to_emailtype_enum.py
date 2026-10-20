"""35_add_new_values_to_emailtype_enum

Revision ID: 2ad1321e81f6
Revises: c97081351f31
Create Date: 2026-10-20 17:36:47.693363

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2ad1321e81f6"
down_revision: str | Sequence[str] | None = "c97081351f31"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'ACCOUNT_ACTIVATED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
