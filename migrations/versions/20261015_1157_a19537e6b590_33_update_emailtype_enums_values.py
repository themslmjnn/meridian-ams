"""33_update_emailtype_enums_values

Revision ID: a19537e6b590
Revises: d624cf852e5f
Create Date: 2026-10-15 11:57:57.263646

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a19537e6b590"
down_revision: str | Sequence[str] | None = "d624cf852e5f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("ALTER TYPE emailtype RENAME VALUE 'ACTIVATION' TO 'ACCOUNT_ACTIVATION'")


def downgrade() -> None:
    """Downgrade schema."""
    op.execute("ALTER TYPE emailtype RENAME VALUE 'ACCOUNT_ACTIVATION' TO 'ACTIVATION'")
