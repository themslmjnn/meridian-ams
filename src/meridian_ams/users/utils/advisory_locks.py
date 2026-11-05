import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.core.advisory_locks import (
    NAMESPACE_EMAIL,
    NAMESPACE_PHONE_NUMBER,
    compute_lock_key,
)

logger = structlog.get_logger(__name__)


ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(:ns, :key)"


async def acquire_contact_locks(
    db_session: AsyncSession,
    *,
    phone_number: str | None,
    email: str | None,
    is_student: bool | None,
) -> None:
    if phone_number:
        key = compute_lock_key(phone_number)

        logger.debug(
            "acquiring_advisory_lock",
            lock_type="phone_number",
            namespace=NAMESPACE_PHONE_NUMBER,
            key=key,
        )

        await db_session.execute(
            text(ADVISORY_LOCK_SQL),
            {"ns": NAMESPACE_PHONE_NUMBER, "key": key},
        )

        logger.debug(
            "advisory_lock_acquired",
            lock_type="phone_number",
            namespace=NAMESPACE_PHONE_NUMBER,
            key=key,
        )

    if email and is_student:
        key = compute_lock_key(email)

        logger.debug(
            "acquiring_advisory_lock",
            lock_type="student_email",
            namespace=NAMESPACE_EMAIL,
            key=key,
        )

        await db_session.execute(
            text(ADVISORY_LOCK_SQL),
            {"ns": NAMESPACE_EMAIL, "key": key},
        )

        logger.debug(
            "advisory_lock_acquired",
            lock_type="student_email",
            namespace=NAMESPACE_EMAIL,
            key=key,
        )
