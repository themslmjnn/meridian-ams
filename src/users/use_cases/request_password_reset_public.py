import uuid

import structlog
from fastapi import status
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency.service import (
    acquire_idempotency_lock,
    complete_idempotency_record,
    hash_payload,
    mirror_complete_to_redis_after_commit,
)
from src.core.idempotency.utils.enums import IdempotencyOperation
from src.users.services.system_admin import UserService

logger = structlog.get_logger(__name__)


class RequestPasswordResetPublicUseCase:
    @staticmethod
    async def execute(
        db_session: AsyncSession,
        redis: Redis,
        *,
        actor_id: int,
        public_id: uuid.UUID,
        idempotency_key: str,
    ) -> None:
        payload_hash = hash_payload(
            {
                "public_id": str(public_id),
            }
        )

        await acquire_idempotency_lock(
            db_session,
            redis,
            operation=IdempotencyOperation.ADMIN_RESET_PASSWORD,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        await UserService.request_password_reset_public(
            session=db_session,
            current_user_id=actor_id,
            public_id=public_id,
        )

        await complete_idempotency_record(
            db_session,
            operation=IdempotencyOperation.ADMIN_RESET_PASSWORD,
            actor_id=actor_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_204_NO_CONTENT,
            body=None,
        )

        await db_session.commit()

        try:
            await mirror_complete_to_redis_after_commit(
                redis,
                operation=IdempotencyOperation.ADMIN_RESET_PASSWORD,
                actor_id=actor_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                http_status=status.HTTP_204_NO_CONTENT,
                body=None,
            )

        except RedisError as exc:
            logger.warning(
                "idempotency_redis_mirror_failed",
                actor_id=actor_id,
                operation=IdempotencyOperation.ADMIN_RESET_PASSWORD,
                error=str(exc),
            )
