import asyncio
from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.advisory_locks import acquire_contact_locks
from src.core.caching import delete_cache
from src.core.dependencies import CurrentUser
from src.emails.utils.enums import EmailType
from src.users.repository.user import (
    UserCredentialsRepository,
    UserIdentityRepository,
    UserSessionRepository,
)
from src.users.schemas.guardian import UpdateProfileGuardian
from src.users.utils.constants import DELETION_GRACE_PERIOD_DAYS
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    GuardianAlreadyPendingDeletionError,
    InvalidStatusTransitionError,
    handle_non_student_unique_contact_error,
)
from src.users.utils.helpers import check_contact_limit
from src.users.utils.schemas import LoadOptionsSchema
from src.utils import email as emails
from src.utils.cache_keys import SessionCacheKey, UserCacheKey
from src.utils.exceptions import raise_unhandled_integrity_error
from src.utils.helpers import update_object

logger = structlog.get_logger(__name__)


class UserServiceGuardian:
    @staticmethod
    async def create_guardian_self_deletion_request(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_id(
            session,
            current_user_id,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if user_credentials is None:
            raise CredentialsNotFoundError()

        if user_credentials.status == UserStatus.PENDING_DELETION:
            logger.warning(
                "guardian_self_deletion_request_denied",
                guardian_id=current_user_id,
                denial_reason="guardian_is_already_pending_deletion",
            )

            raise GuardianAlreadyPendingDeletionError()

        if user_credentials.status != UserStatus.ACTIVE:
            raise InvalidStatusTransitionError()

        user_email = user_credentials.email
        user_public_id = user_credentials.public_id
        deletion_scheduled_for = datetime.now(UTC) + timedelta(
            days=DELETION_GRACE_PERIOD_DAYS
        )

        user_credentials.pre_deletion_status = user_credentials.status
        user_credentials.status = UserStatus.PENDING_DELETION
        user_credentials.deletion_scheduled_for = deletion_scheduled_for

        await UserSessionRepository.invalidate_all_sessions(
            session, user_credentials.sessions
        )

        await session.commit()

        asyncio.create_task(
            emails.send_email_safe(
                emails.send_account_deletion_email(user_email),
                email_type=EmailType.ACCOUNT_DELETION,
            )
        )

        await delete_cache(
            redis,
            SessionCacheKey.access_token_version_key(current_user_id),
            UserCacheKey.user_detail_key_admin(current_user_id),
            UserCacheKey.user_detail_key_self(current_user_id),
        )

        logger.info(
            "guardian_self_deletion_scheduled",
            user_id=current_user_id,
            public_id=user_public_id,
            deletion_scheduled_for=deletion_scheduled_for.isoformat(),
        )

    @staticmethod
    async def update_profile(
        session: AsyncSession,
        redis: Redis,
        current_user: CurrentUser,
        payload: UpdateProfileGuardian,
    ) -> None:
        user_credentials = await UserCredentialsRepository.get_by_public_id(
            session, current_user.public_id
        )
        if user_credentials is None:
            raise CredentialsNotFoundError()

        user_identity = await UserIdentityRepository.get_by_id(
            session, user_credentials.identity_id
        )

        is_phone_number_changing = (
            payload.phone_number is not None
            and payload.phone_number != user_identity.phone_number
        )

        phone_number = payload.phone_number if is_phone_number_changing else None

        await acquire_contact_locks(
            session,
            phone_number=phone_number,
            email=None,
            is_student=False,
        )

        await check_contact_limit(
            session,
            current_user.credentials_id,
            username=user_credentials.username,
            phone_number=phone_number,
            email=None,
            resolved_role=UserRole.GUARDIAN,
            account_type=AccountType.PERSONAL,
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
                UserCacheKey.user_detail_key_admin(current_user.public_id),
                UserCacheKey.user_detail_key_self(current_user.public_id),
            )

            logger.info(
                "user_profile_updated",
                public_id=current_user.public_id,
                method="self_update",
            )

        except IntegrityError as exc:
            await session.rollback()

            logger.error(
                "profile_update_failed",
                public_id=current_user.public_id,
                reason=str(exc.orig),
            )

            handle_non_student_unique_contact_error(exc)
            raise_unhandled_integrity_error(exc)
