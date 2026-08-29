import hashlib

import structlog
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.utils.enums import AccountType

logger = structlog.get_logger(__name__)

NAMESPACE_PHONE = 9001
NAMESPACE_STUDENT_EMAIL = 9002

ADVISORY_LOCK_SQL = "SELECT pg_advisory_xact_lock(:ns, :key)"


def _compute_lock_key(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    unsigned = int.from_bytes(digest[:4], byteorder="big", signed=False)

    return unsigned - 2**32 if unsigned >= 2**31 else unsigned


async def acquire_contact_locks(
    session: AsyncSession,
    *,
    phone_number: str | None,
    email: str | None,
    account_type: AccountType,
) -> None:
    if phone_number:
        key = _compute_lock_key(phone_number)

        logger.debug(
            "acquiring_advisory_lock",
            lock_type="student_phone",
            namespace=NAMESPACE_PHONE,
            key=key,
        )

        await session.execute(
            text(ADVISORY_LOCK_SQL),
            {"ns": NAMESPACE_PHONE, "key": key},
        )

        logger.debug(
            "advisory_lock_acquired",
            lock_type="student_phone",
            namespace=NAMESPACE_PHONE,
            key=key,
        )

    if email and account_type == AccountType.STUDENT:
        key = _compute_lock_key(email)

        logger.debug(
            "acquiring_advisory_lock",
            lock_type="student_email",
            namespace=NAMESPACE_STUDENT_EMAIL,
            key=key,
        )

        await session.execute(
            text(ADVISORY_LOCK_SQL),
            {"ns": NAMESPACE_STUDENT_EMAIL, "key": key},
        )

        logger.debug(
            "advisory_lock_acquired",
            lock_type="student_email",
            namespace=NAMESPACE_STUDENT_EMAIL,
            key=key,
        )
