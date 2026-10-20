from __future__ import annotations

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
from src.users.schemas.system_admin import CreateUserRequest, UserResponseDetailed
from src.users.services.system_admin import UserService

logger = structlog.get_logger(__name__)


class RegisterUserUseCase:
    """Coordinates idempotency and user registration in a single transaction."""

    @staticmethod
    async def execute(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        payload: CreateUserRequest,
        idempotency_key: str,
    ) -> UserResponseDetailed:
        """
        Registers a user under a single atomic transaction.

        All writes — idempotency record, user, activation, email — commit together.
        A failure at any point rolls back everything, leaving the idempotency key
        unclaimed so the client can retry with the same key.

        Redis mirror runs after commit and is best-effort; failure is logged but
        does not affect the response.
        """

        payload_hash = hash_payload(payload.model_dump(mode="json"))

        await acquire_idempotency_lock(
            db_session,
            redis,
            actor_id=actor_id,
            operation=IdempotencyOperation.REGISTER_USER,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        result = await UserService.register_user(db_session, actor_id, payload)

        response = UserResponseDetailed.model_validate(result)

        await complete_idempotency_record(
            db_session,
            actor_id=actor_id,
            operation=IdempotencyOperation.REGISTER_USER,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_201_CREATED,
            body=response.model_dump(mode="json"),
        )

        await db_session.commit()

        try:
            await mirror_complete_to_redis_after_commit(
                redis,
                actor_id=actor_id,
                operation=IdempotencyOperation.REGISTER_USER,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                http_status=status.HTTP_201_CREATED,
                body=response.model_dump(mode="json"),
            )

        except RedisError as exc:
            logger.warning(
                "idempotency_redis_mirror_failed",
                actor_id=actor_id,
                operation=IdempotencyOperation.REGISTER_USER,
                error=str(exc),
            )

        return response
