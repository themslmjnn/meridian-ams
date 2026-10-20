from datetime import UTC, datetime, timedelta

import structlog
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import delete_cache
from src.core.email.service import send_email_in_background
from src.emails.templates import account
from src.emails.utils.enums import EmailType
from src.users.repository.credentials import UserCredentialsRepository
from src.users.repository.session import UserSessionRepository
from src.users.utils.constants import DELETION_GRACE_PERIOD_DAYS
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    GuardianAlreadyPendingDeletionError,
    InvalidStatusTransitionError,
)
from src.users.utils.schemas import LoadOptionsSchema
from src.utils.cache_keys import SessionCacheKey, UserCacheKey

logger = structlog.get_logger(__name__)


class UserServiceGuardian:
    @staticmethod
    async def create_guardian_self_deletion_request(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
    ) -> None:
        credentials = await UserCredentialsRepository.get_by_id(
            db_session,
            actor_id,
            load_options=LoadOptionsSchema(load_sessions=True),
        )
        if credentials is None:
            raise CredentialsNotFoundError()

        if credentials.status == UserStatus.PENDING_DELETION:
            logger.warning(
                "guardian_self_deletion_request_denied",
                actor_id=actor_id,
                denial_reason="guardian_is_already_pending_deletion",
            )

            raise GuardianAlreadyPendingDeletionError()

        if credentials.status != UserStatus.ACTIVE:
            raise InvalidStatusTransitionError()

        deletion_scheduled_for = datetime.now(UTC) + timedelta(
            days=DELETION_GRACE_PERIOD_DAYS
        )

        credentials.pre_transition_status = credentials.status
        credentials.status = UserStatus.PENDING_DELETION
        credentials.deletion_scheduled_for = deletion_scheduled_for

        session_ids = [s.id for s in credentials.sessions]

        await UserSessionRepository.invalidate_all_sessions(credentials.sessions)

        await delete_cache(
            redis,
            *[
                SessionCacheKey.access_token_version_key(session_id)
                for session_id in session_ids
            ],
            UserCacheKey.user_detail_key_admin(actor_id),
            UserCacheKey.user_detail_key_self(actor_id),
        )

        await db_session.commit()

        send_email_in_background(
            account.send_guardian_deletion_email(credentials.email),
            email_type=EmailType.SELF_ACCOUNT_DELETION,
        )

        logger.info(
            "guardian_self_deletion_scheduled",
            user_id=actor_id,
            public_id=credentials.public_id,
            deletion_scheduled_for=deletion_scheduled_for.isoformat(),
        )
