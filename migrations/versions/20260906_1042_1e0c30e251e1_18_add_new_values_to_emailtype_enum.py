"""18_add_new_values_to_emailtype_enum

Revision ID: 1e0c30e251e1
Revises: ce1de058a2eb
Create Date: 2026-09-06 10:42:26.871863

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1e0c30e251e1"
down_revision: str | Sequence[str] | None = "ce1de058a2eb"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'ACCOUNT_DELETION'")
    op.execute("ALTER TYPE emailtype ADD VALUE 'CANCEL_ACCOUNT_DELETION'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
