import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.repository.user import UserCredentialsRepository
from src.users.utils.constants import (
    STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT,
    STUDENT_MAX_SHARED_CONTACT,
)
from src.users.utils.enums import AccountType, UserRole
from src.users.utils.exceptions import (
    DuplicatePhoneNumberError,
    MaxStudentsPerEmailError,
    MaxStudentsPerPhoneNumberError,
)

logger = structlog.get_logger(__name__)


async def check_contact_limit(
    session: AsyncSession,
    current_user_id: int,
    *,
    target_username: str,
    phone_number: str | None,
    email: str | None,
    resolved_role: UserRole,
    account_type: AccountType,
    exclude_credentials_id: int | None = None,
) -> None:
    is_student = account_type == AccountType.STUDENT

    if phone_number is not None:
        phone_count = await UserCredentialsRepository.count_by_phone_and_account_type(
            session,
            phone_number,
            account_type,
            exclude_credentials_id=exclude_credentials_id,
        )

        limit = (
            STUDENT_MAX_SHARED_CONTACT
            if is_student
            else STAFF_AND_GUARDIAN_MAX_SHARED_CONTACT
        )

        if phone_count >= limit:
            logger.warning(
                "user_registration_denied",
                actor_user_id=current_user_id,
                target_username=target_username,
                requested_role=resolved_role,
                denial_reason="maximum_number_of_identical_phone_numbers_reached",
            )

            if is_student:
                raise MaxStudentsPerPhoneNumberError()

            raise DuplicatePhoneNumberError()

    if email is not None and is_student:
        email_count = await UserCredentialsRepository.count_by_email_and_account_type(
            session,
            email,
            account_type,
            exclude_credentials_id=exclude_credentials_id,
        )

        if email_count >= STUDENT_MAX_SHARED_CONTACT:
            logger.warning(
                "user_registration_denied",
                actor_user_id=current_user_id,
                target_username=target_username,
                requested_role=resolved_role,
                denial_reason="maximum_number_of_identical_emails_reached",
            )

            if is_student:
                raise MaxStudentsPerEmailError()
