import uuid
from datetime import UTC, datetime, timedelta
from types import MappingProxyType
from typing import Final, assert_never

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth.models.activation import UserActivation
from meridian_ams.auth.models.login_lockout import UserLoginLockout
from meridian_ams.core.config import get_settings
from meridian_ams.core.email.templates.auth import build_account_activation_email
from meridian_ams.core.security import generate_token
from meridian_ams.emails.enums import EmailType
from meridian_ams.emails.models import Email
from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.models.identity import UserIdentity
from meridian_ams.users.repositories.base import UserResponseRepository
from meridian_ams.users.repositories.credentials import UserCredentialsRepository
from meridian_ams.users.schemas.system_admin import (
    CreateGuardianAdmin,
    CreateStaffAdmin,
    CreateStudentAdmin,
    CreateUserFromExistingIdentityAdmin,
    CreateUserRequest,
    UserResponseDetailedAdmin,
)
from meridian_ams.users.utils.advisory_locks import acquire_contact_locks
from meridian_ams.users.utils.constants import ALUMNI_STATUSES, NON_STUDENT_MIN_AGE
from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
from meridian_ams.users.utils.exceptions import (
    CredentialsAlreadyExistsError,
    IdentityBelowMinimumAgeError,
    IdentityNotFoundError,
    StudentNotEligibleForAdditionalAccountError,
    handle_account_per_identity_error,
    handle_non_student_unique_email_error,
    handle_username_integrity_error,
)
from meridian_ams.users.utils.helpers import calculate_age, check_contact_limit
from meridian_ams.users.utils.schemas import LoadOptionsSchema
from meridian_ams.utils.exceptions import raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)

ACCOUNT_TYPE_BY_ROLE: Final = MappingProxyType(
    {
        UserRole.STUDENT: AccountType.STUDENT,
        UserRole.TEACHER: AccountType.WORK,
        UserRole.DIRECTOR: AccountType.WORK,
        UserRole.GUARDIAN: AccountType.PERSONAL,
    }
)

NewIdentityPayload = CreateStudentAdmin | CreateStaffAdmin | CreateGuardianAdmin


def _resolve_role(payload: CreateUserRequest) -> UserRole:
    match payload:
        case CreateStudentAdmin():
            return UserRole.STUDENT
        case CreateGuardianAdmin():
            return UserRole.GUARDIAN
        case CreateStaffAdmin() | CreateUserFromExistingIdentityAdmin():
            return payload.role
        case _:
            assert_never(payload)


async def _create_identity(
    db_session: AsyncSession, payload: NewIdentityPayload
) -> int:
    identity = UserIdentity(
        first_name=payload.first_name,
        last_name=payload.last_name,
        middle_name=payload.middle_name,
        phone_number=payload.phone_number,
        date_of_birth=payload.date_of_birth,
        address=payload.address,
    )

    db_session.add(identity)
    await db_session.flush()

    return identity.id


async def _resolve_existing_identity_id(
    db_session: AsyncSession,
    existing_user_public_id: uuid.UUID,
    account_type: AccountType,
) -> int:
    referenced = await UserCredentialsRepository.get_by_public_id(
        db_session,
        existing_user_public_id,
        load_options=LoadOptionsSchema(load_identity=True),
    )
    if referenced is None:
        raise IdentityNotFoundError()

    identity = referenced.identity

    student_account = await UserCredentialsRepository.get_by_identity_id(
        db_session, identity.id, AccountType.STUDENT
    )
    if student_account is not None and student_account.status not in ALUMNI_STATUSES:
        raise StudentNotEligibleForAdditionalAccountError(
            f"Student account is {student_account.status.value}; "
            "only graduated students can be given an additional account"
        )

    if (
        identity.date_of_birth is not None
        and calculate_age(identity.date_of_birth) < NON_STUDENT_MIN_AGE
    ):
        raise IdentityBelowMinimumAgeError(
            f"Identity must be at least {NON_STUDENT_MIN_AGE} years old"
        )

    existing_credentials = await UserCredentialsRepository.get_by_identity_id(
        db_session, identity.id, account_type
    )
    if existing_credentials is not None:
        raise CredentialsAlreadyExistsError()

    return identity.id


class UserServiceAdmin:
    @staticmethod
    async def register_user(
        db_session: AsyncSession,
        actor_id: int,
        payload: CreateUserRequest,
    ) -> UserResponseDetailedAdmin:
        settings = get_settings()

        resolved_role = _resolve_role(payload)
        account_type = ACCOUNT_TYPE_BY_ROLE[resolved_role]

        existing_identity_id: int | None = None
        phone_number: str | None = None

        if isinstance(payload, CreateUserFromExistingIdentityAdmin):
            existing_identity_id = await _resolve_existing_identity_id(
                db_session, payload.existing_user_public_id, account_type
            )
        else:
            phone_number = payload.phone_number

        is_student = account_type == AccountType.STUDENT

        await acquire_contact_locks(
            db_session,
            phone_number=phone_number,
            email=payload.email,
            is_student=is_student,
        )

        await check_contact_limit(
            db_session,
            actor_id,
            operation="user_registration",
            username=payload.username,
            phone_number=phone_number,
            email=payload.email,
            account_type=account_type,
            resolved_role=resolved_role,
        )

        raw_activation_token, hashed_activation_token = generate_token()
        activation_token_expires_at = datetime.now(UTC) + timedelta(
            hours=settings.ACTIVATION_TOKEN_EXPIRES_HOURS
        )

        try:
            if existing_identity_id is None:
                assert not isinstance(payload, CreateUserFromExistingIdentityAdmin)

                identity_id = await _create_identity(db_session, payload)
            else:
                identity_id = existing_identity_id

            credentials = UserCredentials(
                identity_id=identity_id,
                username=payload.username,
                email=payload.email,
                role=resolved_role,
                account_type=account_type,
                status=UserStatus.PENDING_ACTIVATION,
            )

            db_session.add(credentials)
            await db_session.flush()

            db_session.add(
                UserActivation(
                    credentials_id=credentials.id,
                    activation_token_hash=hashed_activation_token,
                    activation_token_expires_at=activation_token_expires_at,
                )
            )

            db_session.add(UserLoginLockout(credentials_id=credentials.id))

            subject, html_body = build_account_activation_email(
                payload.username, raw_activation_token
            )

            db_session.add(
                Email(
                    recipient_email=payload.email,
                    subject=subject,
                    html_body=html_body,
                    email_type=EmailType.ACCOUNT_ACTIVATION,
                    triggered_by=actor_id,
                )
            )

            await db_session.flush()

            logger.info(
                "user_registered",
                identity_id=identity_id,
                credentials_id=credentials.id,
                public_id=str(credentials.public_id),
                role=resolved_role,
                created_by=actor_id,
            )

            return await UserResponseRepository.get_registered_user_response(
                db_session, credentials.public_id
            )

        except IntegrityError as exc:
            await db_session.rollback()

            logger.warning(
                "user_registration_failed",
                failure_reason="integrity_error",
                error=repr(exc),
                requested_by=actor_id,
            )

            handle_username_integrity_error(exc)

            if not is_student:
                handle_non_student_unique_email_error(exc)
                handle_account_per_identity_error(exc)

            raise_unhandled_integrity_error(exc)
