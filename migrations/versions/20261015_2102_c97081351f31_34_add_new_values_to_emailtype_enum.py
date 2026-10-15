"""34_add_new_values_to_emailtype_enum

Revision ID: c97081351f31
Revises: c3c2cf313980
Create Date: 2026-10-15 21:02:23.348121

"""
from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'c97081351f31'
down_revision: str | Sequence[str] | None = 'c3c2cf313980'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'GUARDIAN_ACCOUNT_REACTIVATED'")


def downgrade() -> None:
    """Downgrade schema."""
    pass

