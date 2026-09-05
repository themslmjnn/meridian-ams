"""14_make_create_at_required_in_login_history

Revision ID: 21bf6cb4c22e
Revises: b03552951453
Create Date: 2026-09-05 23:53:20.727535

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "21bf6cb4c22e"
down_revision: str | Sequence[str] | None = "b03552951453"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute("UPDATE login_history SET created_at = now() WHERE created_at IS NULL")

    op.alter_column(
        "login_history",
        "created_at",
        nullable=False,
        server_default=sa.func.now(),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        "login_history",
        "created_at",
        nullable=False,
        server_default=None,
    )
