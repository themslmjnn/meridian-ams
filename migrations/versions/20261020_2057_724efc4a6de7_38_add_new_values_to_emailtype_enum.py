"""38_add_new_values_to_emailtype_enum

Revision ID: 724efc4a6de7
Revises: 2dea40779129
Create Date: 2026-10-20 20:57:09.311331

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "724efc4a6de7"
down_revision: str | Sequence[str] | None = "2dea40779129"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype ADD VALUE 'SELF_PROFILE_UPDATING'")


def downgrade() -> None:
    """Downgrade schema."""
    pass
