from datetime import UTC, datetime, timedelta
from typing import assert_never

import structlog
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.auth.models.activation import UserActivation
from meridian_ams.auth.models.login_lockout import UserLoginLockout
from meridian_ams.core.email.templates.auth import build_account_activation_email
from meridian_ams.core.security import generate_token
from meridian_ams.emails.enums import EmailType
from meridian_ams.emails.models import Email
from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.models.identity import UserIdentity
from meridian_ams.users.repositories.base import UserResponseRepository
from meridian_ams.users.repositories.credentials import UserCredentialsRepository
from meridian_ams.users.repositories.identity import UserIdentityRepository
from meridian_ams.users.schemas.system_admin import (
    CreateGuardianFromExistingIdentity,
    CreateNewGuardian,
    CreateStaff,
    CreateStudent,
    CreateUserRequest,
    UserResponseDetailedAdmin,
)
from meridian_ams.users.utils.advisory_locks import acquire_contact_locks
from meridian_ams.users.utils.enums import AccountType, UserRole, UserStatus
from meridian_ams.users.utils.exceptions import (
    GuardianAccountAlreadyExistsError,
    IdentityNotFoundError,
    handle_account_per_identity_error,
    handle_non_student_unique_email_error,
    handle_username_integrity_error,
)
from meridian_ams.users.utils.helpers import check_contact_limit
from meridian_ams.utils.exceptions import raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class UserServiceAdmin:
    @staticmethod
    async def register_user(
        request: Request,
        db_session: AsyncSession,
        actor_id: int,
        payload: CreateUserRequest,
    ) -> UserResponseDetailedAdmin:
        settings = request.app.state.settings

        is_existing_identity = False

        match payload:
            case CreateStudent(type="student"):
                resolved_role = UserRole.STUDENT
                account_type = AccountType.STUDENT

            case CreateStaff(type="staff"):
                resolved_role = payload.role
                account_type = AccountType.WORK

            case CreateNewGuardian(type="new_guardian"):
                resolved_role = UserRole.GUARDIAN
                account_type = AccountType.PERSONAL

            case CreateGuardianFromExistingIdentity(type="existing_identity"):
                resolved_role = UserRole.GUARDIAN
                account_type = AccountType.PERSONAL
                is_existing_identity = True

            case _:
                assert_never(payload)

        is_student = resolved_role == UserRole.STUDENT

        phone_number = None if is_existing_identity else payload.phone_number

        await acquire_contact_locks(
            db_session,
            phone_number=phone_number,
            email=payload.email,
        )

        await check_contact_limit(
            db_session,
            actor_id,
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
            if is_existing_identity:
                guardian_identity = await UserIdentityRepository.get_by_id(
                    db_session, payload.existing_identity_id
                )
                if guardian_identity is None:
                    raise IdentityNotFoundError()

                guardian_credentials = await UserCredentialsRepository.get_personal_accounts_by_identity_id(
                    db_session, guardian_identity.id
                )
                if guardian_credentials is not None:
                    raise GuardianAccountAlreadyExistsError()

                identity_id = payload.existing_identity_id
            else:
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

                identity_id = identity.id

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

            subject, html_body = build_account_activation_email(
                payload.username, raw_activation_token
            )

            db_session.add(
                UserActivation(
                    credentials_id=credentials.id,
                    activation_token_hash=hashed_activation_token,
                    activation_token_expires_at=activation_token_expires_at,
                )
            )
            db_session.add(UserLoginLockout(credentials_id=credentials.id))
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
