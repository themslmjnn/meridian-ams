from datetime import UTC, datetime, timedelta
from typing import assert_never

import structlog
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.advisory_locks import acquire_contact_locks
from src.core.config import get_settings
from src.core.security import generate_activation_token
from src.emails.models import Email
from src.emails.utils.enums import EmailType
from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.models.login_lockout import UserLoginLockout
from src.users.repository.user import (
    UserCredentialsRepository,
    UserIdentityRepository,
    UserRepositoryBase,
)
from src.users.schemas.system_admin import (
    CreateGuardianAdmin,
    CreateStaffAdmin,
    CreateStudentAdmin,
    CreateUserRequest,
    UserResponseAdminDetailed,
)
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import (
    GuardianAccountAlreadyExistsError,
    IdentityNotFoundError,
    handle_non_student_unique_contact_error,
    handle_username_integrity_error,
)
from src.users.utils.helpers import check_contact_limit
from src.utils import email as emails
from src.utils.exceptions import raise_unhandled_integrity_error

logger = structlog.get_logger(__name__)


class UserServiceAdmin:
    @staticmethod
    async def register_user(
        session: AsyncSession,
        current_user_id: int,
        create_request: CreateUserRequest,
    ) -> UserResponseAdminDetailed:
        match create_request:
            case CreateStudentAdmin():
                resolved_role = UserRole.STUDENT
                account_type = AccountType.STUDENT

            case CreateStaffAdmin():
                resolved_role = create_request.role
                account_type = AccountType.WORK

            case CreateGuardianAdmin():
                resolved_role = UserRole.GUARDIAN
                account_type = AccountType.PERSONAL

            case _:
                assert_never(create_request)

        is_student = resolved_role == UserRole.STUDENT

        await acquire_contact_locks(
            session,
            phone_number=create_request.phone_number,
            email=create_request.email,
            is_student=is_student,
        )

        await check_contact_limit(
            session,
            current_user_id,
            target_username=create_request.username,
            phone_number=create_request.phone_number,
            email=create_request.email,
            account_type=account_type,
            resolved_role=resolved_role,
        )

        raw_activation_token, hashed_activation_token = generate_activation_token()

        activation_token_expires_at = datetime.now(UTC) + timedelta(
            hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS
        )

        try:
            if (
                isinstance(create_request, CreateGuardianAdmin)
                and create_request.existing_identity_id
            ):
                existing_identity = (
                    await UserIdentityRepository.get_user_identity_by_id(
                        session, create_request.existing_identity_id
                    )
                )

                if existing_identity is None:
                    raise IdentityNotFoundError()

                existing_personal = await UserCredentialsRepository.get_personal_credentials_by_identity_id(
                    session, existing_identity.id
                )
                if existing_personal is not None:
                    raise GuardianAccountAlreadyExistsError()

                identity_id = create_request.existing_identity_id
            else:
                new_user_identity = UserIdentity(
                    firstname=create_request.firstname,
                    lastname=create_request.lastname,
                    middlename=create_request.middlename,
                    phone_number=create_request.phone_number,
                    date_of_birth=create_request.date_of_birth if is_student else None,
                    address=create_request.address if is_student else None,
                )

                session.add(new_user_identity)
                await session.flush()

                identity_id = new_user_identity.id

            new_user_credentials = UserCredentials(
                identity_id=identity_id,
                username=create_request.username,
                email=create_request.email,
                role=resolved_role,
                account_type=account_type,
                status=UserStatus.PENDING_ACTIVATION,
            )

            session.add(new_user_credentials)
            await session.flush()

            new_user_activation = UserActivation(
                credentials_id=new_user_credentials.id,
                activation_token_hash=hashed_activation_token,
                activation_token_expires_at=activation_token_expires_at,
            )
            new_user_login_lockout = UserLoginLockout(
                credentials_id=new_user_credentials.id
            )

            subject, html_body = emails.build_activation_email(
                raw_activation_token, create_request.username
            )

            new_email = Email(
                recipient_email=create_request.email,
                subject=subject,
                body_html=html_body,
                email_type=EmailType.ACTIVATION,
                triggered_by=current_user_id,
            )

            session.add(new_user_activation)
            session.add(new_user_login_lockout)
            session.add(new_email)

            await session.commit()

            logger.info(
                "user_registered",
                new_user_identity_id=identity_id,
                new_user_credentials_id=new_user_credentials.id,
                target_username=create_request.username,
                role=resolved_role,
                created_by=current_user_id,
            )

            return await UserRepositoryBase.get_registered_user_response(
                session, new_user_credentials.public_id
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.warning(
                "user_registration_failed",
                reason="integrity_error",
                error=str(exc),
                requested_by=current_user_id,
            )

            handle_username_integrity_error(exc)
            if not is_student:
                handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)
