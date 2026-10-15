"""32_update_emailtype_enums_values

Revision ID: d624cf852e5f
Revises: 5ca937a0214f
Create Date: 2026-10-15 11:26:50.839439

"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "d624cf852e5f"
down_revision: str | Sequence[str] | None = "5ca937a0214f"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'UPDATING_ACCOUNT' TO 'ADMIN_PROFILE_OVERRIDE'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ACCOUNT_DEACTIVATION' TO 'ADMIN_ACCOUNT_DEACTIVATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ACCOUNT_ACTIVATION' TO 'ADMIN_ACCOUNT_ACTIVATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ACCOUNT_DELETION' TO 'ADMIN_ACCOUNT_DELETION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'CANCEL_ACCOUNT_DELETION' "
        "TO 'ADMIN_ACCOUNT_DELETION_CANCELLATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'PASSWORD_RESET_ADMIN' TO 'ADMIN_PASSWORD_RESET'"
    )
    op.execute(
        "ALTER TYPE emailtype RENAME VALUE 'EMAIL_CHANGE_CODE' TO 'EMAIL_CHANGE'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'EMAIL_CHANGED' TO 'EMAIL_CHANGE_CONFIRMATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'PASSWORD_CHANGED' "
        "TO 'PASSWORD_CHANGE_CONFIRMATION'"
    )
    op.execute(
        "ALTER TYPE emailtype RENAME VALUE 'FORGOT_PASSWORD' TO 'PUBLIC_PASSWORD_RESET'"
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER TYPE emailtype RENAME VALUE 'PUBLIC_PASSWORD_RESET' TO 'FORGOT_PASSWORD'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'PASSWORD_CHANGE_CONFIRMATION' TO 'PASSWORD_CHANGED'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'EMAIL_CHANGE_CONFIRMATION' TO 'EMAIL_CHANGED'"
    )
    op.execute(
        "ALTER TYPE emailtype RENAME VALUE 'EMAIL_CHANGE' TO 'EMAIL_CHANGE_CODE'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_PASSWORD_RESET' TO 'PASSWORD_RESET_ADMIN'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_ACCOUNT_DELETION_CANCELLATION' "
        "TO 'CANCEL_ACCOUNT_DELETION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_ACCOUNT_DELETION' TO 'ACCOUNT_DELETION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_ACCOUNT_ACTIVATION' "
        "TO 'ACCOUNT_ACTIVATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_ACCOUNT_DEACTIVATION' "
        "TO 'ACCOUNT_DEACTIVATION'"
    )
    op.execute(
        "ALTER TYPE emailtype "
        "RENAME VALUE 'ADMIN_PROFILE_OVERRIDE' "
        "TO 'UPDATING_ACCOUNT'"
    )
