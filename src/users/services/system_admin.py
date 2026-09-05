import asyncio
import uuid
from datetime import UTC, datetime, timedelta
from typing import assert_never

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

import src.users.schemas.system_admin as schemas
import src.users.utils.constants as constants
import src.users.utils.exceptions as exceptions
from src.core.advisory_locks import acquire_contact_locks
from src.core.caching import delete_cache, get_cache, set_cache
from src.core.config import get_settings
from src.core.pagination import CursorPage
from src.core.security import generate_token
from src.emails.models import Email
from src.emails.utils.enums import EmailType
from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.models.login_lockout import UserLoginLockout
from src.users.models.password_reset import UserPasswordReset
from src.users.repository.user import (
    UserCredentialsRepository,
    UserIdentityRepository,
    UserRepositoryBase,
    UserResponseRepository,
)
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.helpers import check_contact_limit
from src.users.utils.schemas import LoadOptionsSchema
from src.utils import email as emails
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import raise_unhandled_integrity_error
from src.utils.helpers import update_object

logger = structlog.get_logger(__name__)


class UserServiceAdmin:
    @staticmethod
    async def register_user(
        session: AsyncSession,
        current_user_id: int,
        payload: schemas.CreateUserRequest,
    ) -> schemas.UserResponseAdminDetailed:
        match payload:
            case schemas.CreateStudentAdmin():
                resolved_role = UserRole.STUDENT
                account_type = AccountType.STUDENT

            case schemas.CreateStaffAdmin():
                resolved_role = payload.role
                account_type = AccountType.WORK

            case schemas.CreateGuardianAdmin():
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
            username=payload.username,
            phone_number=payload.phone_number,
            email=payload.email,
            account_type=account_type,
            resolved_role=resolved_role,
        )

        raw_activation_token, hashed_activation_token = generate_token()

        activation_token_expires_at = datetime.now(UTC) + timedelta(
            hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS
        )

        try:
            if (
                isinstance(payload, schemas.CreateGuardianAdmin)
                and payload.existing_identity_id
            ):
                existing_identity = await UserIdentityRepository.get_by_id(
                    session, payload.existing_identity_id
                )
                if existing_identity is None:
                    raise exceptions.IdentityNotFoundError()

                existing_personal = await UserCredentialsRepository.get_personal_accounts_by_identity_id(
                    session, existing_identity.id
                )
                if existing_personal is not None:
                    raise exceptions.GuardianAccountAlreadyExistsError()

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
                identity_id=identity_id,
                credentials_id=new_user_credentials.id,
                public_id=str(new_user_credentials.public_id),
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

            exceptions.handle_username_integrity_error(exc)
            if not is_student:
                exceptions.handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def update_user(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
        payload: schemas.UpdateUserRequest,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        user_identity = await UserIdentityRepository.get_by_id(
            session, user_credentials.identity_id
        )

        is_student = user_credentials.role == UserRole.STUDENT
        is_request_student_shaped = isinstance(payload, schemas.UpdateStudentAdmin)

        if is_student != is_request_student_shaped:
            logger.warning(
                "update_payload_mismatch",
                actor_user_id=current_user_id,
                public_id=public_id,
                user_role=user_credentials.role.value,
                submitted_type=payload.type,
            )

            raise exceptions.UpdatePayloadMismatchError()

        is_phone_number_changing = (
            payload.phone_number is not None
            and payload.phone_number != user_identity.phone_number
        )

        if is_phone_number_changing:
            await acquire_contact_locks(
                session,
                phone_number=payload.phone_number,
                email=None,
                is_student=True,
            )

            await check_contact_limit(
                session,
                current_user_id,
                username=user_credentials.username,
                phone_number=payload.phone_number,
                email=None,
                resolved_role=UserRole.STUDENT,
                account_type=AccountType.STUDENT,
                exclude_credentials_id=user_credentials.id,
            )

        try:
            update_object(user_identity, payload)

            await session.commit()

            asyncio.create_task(
                emails.send_email_safe(
                    emails.send_account_info_updated_email(user_credentials.email),
                    email_type=EmailType.UPDATING_ACCOUNT,
                )
            )

            await delete_cache(
                redis,
                UserCacheKey.user_detail_key_admin(public_id),
                UserCacheKey.user_detail_key_staff(public_id),
                UserCacheKey.user_detail_key_self(public_id),
            )

            logger.info(
                "user_profile_updated",
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
                exceptions.handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def update_user_credentials(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
        payload: schemas.UpdateUserCredentials,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(
                load_sessions=True,
                load_activation=True,
                load_email_change=True,
            ),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        is_student = user_credentials.role == UserRole.STUDENT
        is_email_changing = (
            payload.email is not None and payload.email != user_credentials.email
        )
        should_reissue_activation_token = (
            is_email_changing
            and user_credentials.status == UserStatus.PENDING_ACTIVATION
        )

        if is_student and is_email_changing:
            await acquire_contact_locks(
                session, phone_number=None, email=payload.email, is_student=True
            )

            await check_contact_limit(
                session,
                current_user_id,
                username=user_credentials.username,
                phone_number=None,
                email=payload.email,
                resolved_role=UserRole.STUDENT,
                account_type=AccountType.STUDENT,
                exclude_credentials_id=user_credentials.id,
            )

        try:
            old_email = user_credentials.email
            old_username = user_credentials.username

            update_object(user_credentials, payload)

            for session_row in user_credentials.sessions:
                session_row.access_token_version += 1
                session_row.refresh_token_hash = None
                session_row.refresh_token_family = None
                session_row.refresh_token_expires_at = None

            if user_credentials.email_change is not None:
                await session.delete(user_credentials.email_change)

            if should_reissue_activation_token:
                if should_reissue_activation_token is None:
                    raise exceptions.UserAlreadyActiveError()

                raw_activation_token, hashed_activation_token = generate_token()
                activation_token_expires_at = datetime.now(UTC) + timedelta(
                    hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS
                )

                user_credentials.activation.activation_token_hash = (
                    hashed_activation_token
                )
                user_credentials.activation.activation_token_expires_at = (
                    activation_token_expires_at
                )

                subject, html_body = emails.build_activation_email(
                    raw_activation_token, user_credentials.username
                )

                new_pending_email = Email(
                    recipient_email=user_credentials.email,
                    subject=subject,
                    body_html=html_body,
                    email_type=EmailType.ACTIVATION,
                    triggered_by=current_user_id,
                )

                session.add(new_pending_email)

            username_changed = old_username != user_credentials.username
            email_changed = old_email != user_credentials.email

            if not should_reissue_activation_token:
                notify_old_username = old_username if username_changed else None
                notify_new_username = (
                    user_credentials.username if username_changed else None
                )
                notify_old_email = old_email if email_changed else None
                notify_new_email = user_credentials.email if email_changed else None

                subject, html_body = (
                    emails.build_admin_credentials_override_notification_email(
                        notify_old_username,
                        notify_new_username,
                        notify_old_email,
                        notify_new_email,
                    )
                )

                new_email = Email(
                    recipient_email=old_email,
                    subject=subject,
                    body_html=html_body,
                    email_type=EmailType.ADMIN_CREDENTIALS_OVERRIDE,
                    triggered_by=current_user_id,
                )

                session.add(new_email)

            await session.commit()

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

            exceptions.handle_username_integrity_error(exc)
            if not is_student:
                exceptions.handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)

    @staticmethod
    async def deactivate_user(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        if user_credentials.status == UserStatus.DEACTIVATED:
            logger.warning(
                "user_deactivation_failed",
                public_id=public_id,
                requested_by=current_user_id,
                reason="user_is_already_deactivated",
            )

            raise exceptions.UserAlreadyInactiveError()

        if user_credentials.status != UserStatus.ACTIVE:
            raise exceptions.InvalidStatusTransitionError()

        user_credentials.status = UserStatus.DEACTIVATED

        for session_row in user_credentials.sessions:
            session_row.access_token_version += 1
            session_row.refresh_token_hash = None
            session_row.refresh_token_family = None
            session_row.refresh_token_expires_at = None

        await session.commit()

        asyncio.schemas.create_task(
            emails.send_email_safe(
                emails.send_account_deactivation_email(user_credentials.email),
                email_type=EmailType.ACCOUNT_DEACTIVATION,
            )
        )

        await delete_cache(
            redis,
            SessionCacheKey.access_token_version_key(public_id),
            UserCacheKey.user_detail_key_admin(public_id),
            UserCacheKey.user_detail_key_staff(public_id),
            UserCacheKey.user_detail_key_self(public_id),
        )

        logger.info(
            "user_deactivated",
            public_id=public_id,
            deactivated_by=current_user_id,
        )

    @staticmethod
    async def activate_user(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(load_login_lockout=True),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        if user_credentials.status == UserStatus.ACTIVE:
            logger.warning(
                "user_activation_failed",
                public_id=public_id,
                requested_by=current_user_id,
                reason="user_is_already_activated",
            )

            raise exceptions.UserAlreadyActiveError()

        if user_credentials.status != UserStatus.DEACTIVATED:
            raise exceptions.InvalidStatusTransitionError()

        user_credentials.status = UserStatus.ACTIVE

        if user_credentials.login_lockout is not None:
            user_credentials.login_lockout.failed_attempts = 0
            user_credentials.login_lockout.locked_until = None

        await session.commit()

        asyncio.create_task(
            emails.send_email_safe(
                emails.send_account_activation_email(user_credentials.email),
                email_type=EmailType.ACCOUNT_ACTIVATION,
            )
        )

        await delete_cache(
            redis,
            UserCacheKey.user_detail_key_admin(public_id),
            UserCacheKey.user_detail_key_staff(public_id),
            UserCacheKey.user_detail_key_self(public_id),
        )

        logger.info(
            "user_activated",
            public_id=public_id,
            activated_by=current_user_id,
        )

    @staticmethod
    async def create_reset_password_request(
        session: AsyncSession,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(load_password_reset=True),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        if user_credentials.status != UserStatus.ACTIVE:
            raise exceptions.InvalidStatusTransitionError()

        raw_reset_token, hashed_reset_token = generate_token()

        if user_credentials.password_reset is None:
            new_password_reset = UserPasswordReset(
                credentials_id=user_credentials.id,
                reset_password_token_hash=hashed_reset_token,
                reset_password_token_expires_at=datetime.now(UTC)
                + timedelta(minutes=get_settings().RESET_PASSWORD_EXPIRES_MINUTES),
            )

            session.add(new_password_reset)
        else:
            user_credentials.password_reset.reset_password_token_hash = (
                hashed_reset_token
            )
            user_credentials.password_reset.reset_password_token_expires_at = (
                datetime.now(UTC)
                + timedelta(minutes=get_settings().RESET_PASSWORD_EXPIRES_MINUTES)
            )

        subject, html_body = emails.build_reset_password_email(raw_reset_token)

        new_email = Email(
            recipient_email=user_credentials.email,
            subject=subject,
            body_html=html_body,
            email_type=EmailType.PASSWORD_RESET_ADMIN,
            triggered_by=current_user_id,
        )

        session.add(new_email)
        await session.commit()

        logger.info(
            "reset_password_request_schemas.created",
            public_id=public_id,
            created_by=current_user_id,
        )

    @staticmethod
    async def resend_activation_invite(
        session: AsyncSession,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            excluded_roles=constants.SYSTEM_ADMIN_INVISIBLE_ROLES,
            load_options=LoadOptionsSchema(
                load_activation=True,
            ),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        if user_credentials.status != UserStatus.PENDING_ACTIVATION:
            logger.warning(
                "invite_resend_denied",
                public_id=public_id,
                actor_user_id=current_user_id,
                denial_reason="user_not_pending_activation",
            )

            raise exceptions.UserNotPendingActivationError()

        if user_credentials.activation is None:
            logger.error(
                "user_is_already_active",
                public_id=public_id,
                status=user_credentials.status,
            )

            raise exceptions.UserAlreadyActiveError()

        raw_activation_token, hashed_activation_token = generate_token()

        activation_token_expires_at = datetime.now(UTC) + timedelta(
            hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS
        )

        user_credentials.activation.activation_token_hash = hashed_activation_token
        user_credentials.activation.activation_token_expires_at = (
            activation_token_expires_at
        )

        subject, html_body = emails.build_activation_email(
            raw_activation_token, user_credentials.username
        )

        new_email = Email(
            recipient_email=user_credentials.email,
            subject=subject,
            body_html=html_body,
            email_type=EmailType.ACTIVATION,
            triggered_by=current_user_id,
        )

        session.add(new_email)
        await session.commit()

        logger.info(
            "invite_resent",
            public_id=public_id,
            actor_user_id=current_user_id,
        )

    @staticmethod
    async def create_guardian_deletion_request(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
            account_type=AccountType.PERSONAL,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        if user_credentials.status not in (UserStatus.ACTIVE, UserStatus.INACTIVE):
            raise exceptions.InvalidStatusTransitionError()

        if user_credentials.status == UserStatus.PENDING_DELETION:
            logger.warning(
                "guardian_deletion_denied",
                actor_user_id=current_user_id,
                public_id=public_id,
                denial_reason="guardian_already_pending_deletion",
            )

            raise exceptions.GuardianAlreadyPendingDeletionError()

        deletion_scheduled_for = datetime.now(UTC) + timedelta(
            days=constants.DELETION_GRACE_PERIOD_DAYS
        )

        user_credentials.pre_deletion_status = user_credentials.status
        user_credentials.status = UserStatus.PENDING_DELETION
        user_credentials.deletion_scheduled_for = deletion_scheduled_for

        for session_row in user_credentials.sessions:
            session_row.access_token_version += 1
            session_row.refresh_token_hash = None
            session_row.refresh_token_family = None
            session_row.refresh_token_expires_at = None

        user_credentials_email = user_credentials.email

        await session.commit()

        asyncio.create_task(
            emails.send_email_safe(
                emails.send_account_deletion_email(user_credentials_email),
                email_type=EmailType.ACCOUNT_DELETION,
            )
        )

        await delete_cache(
            redis,
            SessionCacheKey.access_token_version_key(public_id),
            UserCacheKey.user_detail_key_admin(public_id),
            UserCacheKey.user_detail_key_self(public_id),
        )

        logger.info(
            "guardian_deletion_scheduled",
            actor_user_id=current_user_id,
            public_id=public_id,
            deletion_scheduled_for=deletion_scheduled_for.isoformat(),
        )

    @staticmethod
    async def cancel_guardian_deletion_request(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session,
            public_id,
        )
        if user_credentials is None:
            raise exceptions.CredentialsNotFoundError()

        user_email = user_credentials.email

        reactivated = await UserCredentialsRepository.reactivate_pending_deletion_user(
            session, public_id
        )

        if not reactivated:
            await session.rollback()

            logger.warning(
                "guardian_deletion_cancel_lost_race",
                actor_user_id=current_user_id,
                public_id=public_id,
                denial_reason="user_hard_deleted_before_cancel_committed",
            )

            raise exceptions.CredentialsNotFoundError()

        await session.commit()

        asyncio.create_task(
            emails.send_email_safe(
                emails.send_account_deletion_canceled_email(user_email),
                email_type=EmailType.CANCEL_ACCOUNT_DELETION,
            )
        )

        await delete_cache(
            redis,
            UserCacheKey.user_detail_key_admin(public_id),
            UserCacheKey.user_detail_key_self(public_id),
        )

        logger.info(
            "guardian_deletion_cancelled",
            actor_user_id=current_user_id,
            public_id=public_id,
        )

    @staticmethod
    async def get_staff(
        session: AsyncSession,
        *,
        filters: schemas.SearchUserBase | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[schemas.UserResponseAdminDetailed]:
        page = await UserRepositoryBase.get_users(
            session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            allowed_roles=constants.STAFF_ROLES,
        )

        return CursorPage[schemas.UserResponseAdminDetailed](
            items=[
                schemas.UserResponseAdminDetailed.model_validate(row)
                for row in page.items
            ],
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            limit=page.limit,
        )

    @staticmethod
    async def get_staff_by_public_id(
        session: AsyncSession, redis: Redis, public_id: uuid.UUID
    ) -> schemas.UserResponseAdminDetailed:
        cache_key = UserCacheKey.user_detail_key_admin(public_id)

        cached = await get_cache(redis, cache_key)

        if cached is not None:
            return schemas.UserResponseAdminDetailed.model_validate(cached)

        staff = await UserRepositoryBase.get_user_by_public_id(
            session, public_id, allowed_roles=constants.STAFF_ROLES
        )
        if staff is None:
            raise exceptions.UserNotFoundError()

        response = schemas.UserResponseAdminDetailed.model_validate(staff)

        await set_cache(redis, cache_key, response.model_dump(mode="json"), 900)

        return response

    @staticmethod
    async def get_guardians(
        session: AsyncSession,
        *,
        filters: schemas.SearchUserBase | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[schemas.UserResponseAdminDetailed]:
        page = await UserRepositoryBase.get_users(
            session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
            allowed_roles=constants.GUARDIAN_ROLE,
        )

        return CursorPage[schemas.UserResponseAdminDetailed](
            items=[
                schemas.UserResponseAdminDetailed.model_validate(row)
                for row in page.items
            ],
            next_cursor=page.next_cursor,
            prev_cursor=page.prev_cursor,
            limit=page.limit,
        )

    @staticmethod
    async def get_guardian_by_public_id(
        session: AsyncSession, redis: Redis, public_id: uuid.UUID
    ) -> schemas.UserResponseAdminDetailed:
        cache_key = UserCacheKey.user_detail_key_admin(public_id)

        cached = await get_cache(redis, cache_key)

        if cached is not None:
            return schemas.UserResponseAdminDetailed.model_validate(cached)

        guardian = await UserRepositoryBase.get_user_by_public_id(
            session, public_id, allowed_roles=constants.GUARDIAN_ROLE
        )
        if guardian is None:
            raise exceptions.UserNotFoundError()

        response = schemas.UserResponseAdminDetailed.model_validate(guardian)

        await set_cache(redis, cache_key, response.model_dump(mode="json"), 900)

        return response
