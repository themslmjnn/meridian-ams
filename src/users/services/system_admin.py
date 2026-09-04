import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import assert_never

import structlog
from fastapi import Request
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.advisory_locks import acquire_contact_locks
from src.core.caching import delete_cache, get_redis
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
    UserResponseRepository,
)
from src.users.schemas.system_admin import (
    CreateGuardianAdmin,
    CreateStaffAdmin,
    CreateStudentAdmin,
    CreateUserRequest,
    UpdateStudentAdmin,
    UpdateUserCredentials,
    UpdateUserRequest,
    UserResponseAdminDetailed,
)
from src.users.utils.constants import SYSTEM_ADMIN_INVISIBLE_ROLES
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import (
    GuardianAccountAlreadyExistsError,
    IdentityNotFoundError,
    UserNotFoundError,
    UserTypeMismatchError,
    handle_non_student_unique_contact_error,
    handle_username_integrity_error,
)
from src.users.utils.helpers import check_contact_limit
from src.users.utils.schemas import LoadOptionsSchema
from src.utils import email as emails
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import raise_unhandled_integrity_error
from src.utils.helpers import ensure_exists, update_object

logger = structlog.get_logger(__name__)


class UserServiceAdmin:
    @staticmethod
    async def register_user(
        session: AsyncSession,
        current_user_id: int,
        payload: CreateUserRequest,
    ) -> UserResponseAdminDetailed:
        match payload:
            case CreateStudentAdmin():
                resolved_role = UserRole.STUDENT
                account_type = AccountType.STUDENT

            case CreateStaffAdmin():
                resolved_role = payload.role
                account_type = AccountType.WORK

            case CreateGuardianAdmin():
                resolved_role = UserRole.GUARDIAN
                account_type = AccountType.PERSONAL

            case _:
                assert_never(payload)

        is_student = resolved_role == UserRole.STUDENT

        await acquire_contact_locks(
            session,
            phone_number=payload.phone_number,
            email=payload.email,
            is_student=is_student,
        )

        await check_contact_limit(
            session,
            current_user_id,
            target_username=payload.username,
            phone_number=payload.phone_number,
            email=payload.email,
            account_type=account_type,
            resolved_role=resolved_role,
        )

        raw_activation_token, hashed_activation_token = generate_activation_token()

        activation_token_expires_at = datetime.now(UTC) + timedelta(
            hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS
        )

        try:
            if (
                isinstance(payload, CreateGuardianAdmin)
                and payload.existing_identity_id
            ):
                existing_identity = await UserIdentityRepository.get_by_id(
                    session, payload.existing_identity_id
                )
                if existing_identity is None:
                    raise IdentityNotFoundError()

                existing_personal = await UserCredentialsRepository.get_personal_accounts_by_identity_id(
                    session, existing_identity.id
                )
                if existing_personal is not None:
                    raise GuardianAccountAlreadyExistsError()

                identity_id = payload.existing_identity_id
            else:
                new_user_identity = UserIdentity(
                    firstname=payload.firstname,
                    lastname=payload.lastname,
                    middlename=payload.middlename,
                    phone_number=payload.phone_number,
                    date_of_birth=payload.date_of_birth if is_student else None,
                    address=payload.address if is_student else None,
                )

                session.add(new_user_identity)
                await session.flush()

                identity_id = new_user_identity.id

            new_user_credentials = UserCredentials(
                identity_id=identity_id,
                username=payload.username,
                email=payload.email,
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
                raw_activation_token, payload.username
            )

            new_email = Email(
                recipient_email=payload.email,
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
                target_username=payload.username,
                role=resolved_role,
                created_by=current_user_id,
            )

            return await UserResponseRepository.get_registered_user_response(
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

    @staticmethod
    async def update_user(
        request: Request,
        session: AsyncSession,
        current_user_id: int,
        public_id: int,
        update_request: UpdateUserRequest,
    ) -> None:
        target_user = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=SYSTEM_ADMIN_INVISIBLE_ROLES,
        )
        ensure_exists(target_user, UserNotFoundError())
        target_identity = await UserIdentityRepository.get_by_id(
            session, target_user.identity_id
        )

        is_student = target_user.role == UserRole.STUDENT
        request_is_student_shaped = isinstance(update_request, UpdateStudentAdmin)

        if is_student != request_is_student_shaped:
            logger.warning(
                "update_user_type_mismatch",
                actor_user_id=current_user_id,
                public_id=public_id,
                target_user_role=target_user.role.value,
                submitted_type=update_request.type,
            )

            raise UserTypeMismatchError()

        phone_number_changing = (
            update_request.phone_number is not None
            and update_request.phone_number != target_identity.phone_number
        )

        if is_student and phone_number_changing:
            await acquire_contact_locks(
                session,
                phone_number=update_request.phone_number,
                email=None,
                is_student=True,
            )

            await check_contact_limit(
                session,
                current_user_id,
                target_username=target_user.username,
                phone_number=update_request.phone_number,
                email=None,
                resolved_role=UserRole.STUDENT,
                account_type=AccountType.STUDENT,
                exclude_credentials_id=target_user.id,
            )

        try:
            update_object(target_identity, update_request)

            await session.commit()
            await session.refresh(target_identity)

            asyncio.create_task(
                emails.send_email_safe(
                    emails.send_account_info_updated_email(target_user.email),
                    email_type=EmailType.UPDATING_ACCOUNT,
                )
            )

            redis = get_redis(request)
            await delete_cache(
                redis,
                UserCacheKey.user_detail_key_admin(public_id),
                UserCacheKey.user_detail_key_staff(public_id),
                UserCacheKey.user_detail_key_self(public_id),
            )

            logger.info(
                "user_updated",
                public_id=public_id,
                updated_by=current_user_id,
                method="admin_update",
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "update_user_failed",
                public_id=public_id,
                requested_by=current_user_id,
                reason=str(exc.orig),
                method="admin_update",
            )

            if not is_student:
                handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def update_user_credentials(
        request: Request,
        session: AsyncSession,
        current_user_id: int,
        public_id: uuid.UUID,
        update_request: UpdateUserCredentials,
    ) -> None:
        target_user = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_activation=True,
                load_email_change=True,
            ),
        )
        ensure_exists(target_user, UserNotFoundError())

        is_student = target_user.role == UserRole.STUDENT
        email_changing = (
            update_request.email is not None
            and update_request.email != target_user.email
        )
        should_reissue_activation_token = (
            email_changing and target_user.status == UserStatus.PENDING_ACTIVATION
        )

        if is_student and email_changing:
            await acquire_contact_locks(
                session, phone_number=None, email=update_request.email, is_student=True
            )

            await check_contact_limit(
                session,
                current_user_id,
                target_username=target_user.username,
                phone_number=None,
                email=update_request.email,
                resolved_role=UserRole.STUDENT,
                account_type=AccountType.STUDENT,
                exclude_credentials_id=target_user.id,
            )

        try:
            old_email = target_user.email
            old_username = target_user.username

            update_object(target_user, update_request)

            for session_row in target_user.sessions:
                session_row.access_token_version += 1
                session_row.refresh_token_hash = None
                session_row.refresh_token_family = None
                session_row.refresh_token_expires_at = None

            if target_user.email_change is not None:
                await session.delete(target_user.email_change)

            if should_reissue_activation_token:
                raw_activation_token, hashed_activation_token = (
                    generate_activation_token()
                )
                activation_token_expires_at = datetime.now(UTC) + timedelta(
                    hours=get_settings().INVITE_TOKEN_EXPIRES_HOURS
                )

                target_user.activation.activation_token_hash = hashed_activation_token
                target_user.activation.activation_token_expires_at = (
                    activation_token_expires_at
                )

                subject, html_body = emails.build_activation_email(
                    raw_activation_token, target_user.username
                )

                new_pending_email = Email(
                    recipient=target_user.email,
                    subject=subject,
                    html_body=html_body,
                    email_type=EmailType.ACTIVATION,
                    triggered_by=current_user_id,
                )

                session.add(new_pending_email)

            username_changed = old_username != target_user.username
            email_changed = old_email != target_user.email

            if not should_reissue_activation_token:
                notify_old_username = old_username if username_changed else None
                notify_new_username = target_user.username if username_changed else None
                notify_old_email = old_email if email_changed else None
                notify_new_email = target_user.email if email_changed else None

                subject, html_body = (
                    emails.build_admin_credentials_override_notification_email(
                        notify_old_username,
                        notify_new_username,
                        notify_old_email,
                        notify_new_email,
                    )
                )

                new_pending_email = Email(
                    recipient=old_email,
                    subject=subject,
                    html_body=html_body,
                    email_type=EmailType.ADMIN_CREDENTIALS_OVERRIDE,
                    triggered_by=current_user_id,
                )

                session.add(new_pending_email)

            await session.commit()

            redis = get_redis(request)
            await delete_cache(
                redis,
                SessionCacheKey.access_token_version_key(public_id),
                UserCacheKey.user_detail_key_admin(public_id),
                UserCacheKey.user_detail_key_staff(public_id),
                UserCacheKey.user_detail_key_self(public_id),
            )

            logger.info(
                "user_credentials_updated",
                public_id=public_id,
                updated_by=current_user_id,
                method="admin_credentials_override",
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "user_credentials_update_failed",
                public_id=public_id,
                requested_by=current_user_id,
                reason=str(exc.orig),
                method="admin_credentials_override",
            )

            handle_username_integrity_error(exc)
            if not is_student:
                handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)
