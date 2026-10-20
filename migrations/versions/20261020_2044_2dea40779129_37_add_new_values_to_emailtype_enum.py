"""37_add_new_values_to_emailtype_enum

Revision ID: 2dea40779129
Revises: 2dbbad72ef03
Create Date: 2026-10-20 20:44:50.146987

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "2dea40779129"
down_revision: str | Sequence[str] | None = "2dbbad72ef03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'SELF_ACCOUNT_DELETION'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
