"""31_change_refresh_token_family_field_name

Revision ID: 5ca937a0214f
Revises: 4f2e609aa181
Create Date: 2026-10-14 21:20:22.768921

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "5ca937a0214f"
down_revision: str | Sequence[str] | None = "4f2e609aa181"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "user_sessions",
        "refresh_token_family",
        new_column_name="refresh_token_family_hash",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "user_sessions",
        "refresh_token_family_hash",
        new_column_name="refresh_token_family",
    )
