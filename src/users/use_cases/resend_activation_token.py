import uuid

import structlog
from fastapi import status
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency import (
    acquire_idempotency_lock,
    complete_idempotency_record,
    hash_payload,
    mirror_complete_to_redis_after_commit,
)
from src.users.services.system_admin import UserService
from src.utils.enums import IdempotencyOperation

logger = structlog.get_logger(__name__)


class ResendActivationTokentUseCase:
    @staticmethod
    async def execute(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        public_id: uuid.UUID,
        idempotency_key: str,
    ) -> None:
        payload_hash = hash_payload(
            {
                "public_id": str(public_id),
            }
        )

        await acquire_idempotency_lock(
            session,
            redis,
            operation=IdempotencyOperation.RESEND_ACTIVATION_TOKEN,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        await UserService.resend_activation_token(
            session=session,
            current_user_id=current_user_id,
            public_id=public_id,
        )

        await complete_idempotency_record(
            session,
            operation=IdempotencyOperation.RESEND_ACTIVATION_TOKEN,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_204_NO_CONTENT,
            body=None,
        )

        await session.commit()

        try:
            await mirror_complete_to_redis_after_commit(
                redis,
                operation=IdempotencyOperation.RESEND_ACTIVATION_TOKEN,
                actor_id=current_user_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                http_status=status.HTTP_204_NO_CONTENT,
                body=None,
            )

        except RedisError as exc:
            logger.warning(
                "idempotency_redis_mirror_failed",
                actor_id=current_user_id,
                operation=IdempotencyOperation.RESEND_ACTIVATION_TOKEN,
                error=str(exc),
            )
