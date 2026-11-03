import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.users.repositories.credentials import UserCredentialsRepository
from meridian_ams.users.utils.constants import (
    STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT,
    STUDENT_MAX_SHARED_CONTACT,
)
from meridian_ams.users.utils.enums import AccountType, UserRole
from meridian_ams.users.utils.exceptions import (
    DuplicateEmailError,
    DuplicatePhoneNumberError,
    MaxStudentsPerEmailError,
    MaxStudentsPerPhoneNumberError,
)

logger = structlog.get_logger(__name__)


async def check_contact_limit(
    db_session: AsyncSession,
    actor_id: int | None,
    operation: str,
    *,
    username: str,
    phone_number: str | None,
    email: str | None,
    resolved_role: UserRole,
    account_type: AccountType,
    exclude_credentials_id: int | None = None,
) -> None:
    is_student = account_type == AccountType.STUDENT

    limit = (
        STUDENT_MAX_SHARED_CONTACT
        if is_student
        else STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT
    )

    if phone_number is not None:
        phone_count = await UserCredentialsRepository.count_by_phone_and_account_type(
            db_session,
            phone_number,
            account_type,
            exclude_credentials_id=exclude_credentials_id,
        )

        if phone_count >= limit:
            logger.warning(
                f"{operation}_denied",
                actor_id=actor_id,
                username=username,
                requested_role=resolved_role,
                denial_reason="maximum_number_of_identical_phone_numbers_reached",
            )

            if is_student:
                raise MaxStudentsPerPhoneNumberError()

            raise DuplicatePhoneNumberError()

    if email is not None:
        email_count = await UserCredentialsRepository.count_by_email_and_account_type(
            db_session,
            email,
            account_type,
            exclude_credentials_id=exclude_credentials_id,
        )

        if email_count >= limit:
            logger.warning(
                f"{operation}_denied",
                actor_id=actor_id,
                username=username,
                requested_role=resolved_role,
                denial_reason="maximum_number_of_identical_emails_reached",
            )

            if is_student:
                raise MaxStudentsPerEmailError()

            raise DuplicateEmailError()
