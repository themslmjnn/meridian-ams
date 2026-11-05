"""13_update_server_defaults_in_emails_table

Revision ID: 369b8fec70e6
Revises: 275562ea322e
Create Date: 2026-11-05 12:59:40.161591

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "369b8fec70e6"
down_revision: str | Sequence[str] | None = "275562ea322e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        "emails",
        "status",
        server_default="PENDING",
    )
    op.alter_column(
        "emails",
        "retry_count",
        server_default="0",
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "emails",
        "status",
        server_default=None,
    )
    op.alter_column(
        "emails",
        "retry_count",
        server_default=None,
    )
