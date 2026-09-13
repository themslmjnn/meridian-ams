from __future__ import annotations

import structlog
from fastapi import status
from redis import RedisError
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency import (
    _hash_payload,
    acquire_idempotency_lock,
    complete_idempotency_record,
    mirror_complete_to_redis_after_commit,
)
from src.users.schemas.system_admin import CreateUserRequest, UserResponseDetailed
from src.users.services.system_admin import UserService
from src.utils.enums import IdempotencyOperation

logger = structlog.get_logger(__name__)


class RegisterUserUseCase:
    """
    Coordinates idempotency and user registration in a single transaction.

    Responsibilities:
        - Extract and hash the request payload for fingerprinting
        - Acquire the idempotency lock (INSERT PROCESSING, flush only)
        - Delegate business logic to UserService (flush only, no commit)
        - Mark the record COMPLETE (flush only)
        - Commit everything atomically
        - Mirror the result to Redis after commit

    Transaction boundary:
        PROCESSING + user + activation + lockout + email + COMPLETE
        all commit together. Any failure rolls back everything — the
        PROCESSING record disappears and the client can retry freely
        with the same key and corrected payload.

    The router handles: authentication, rate limiting, request parsing, response serialisation.
    UserService handles: domain rules, DB writes, email queuing.
    This class handles: the coordination and transaction boundary.
    """

    @staticmethod
    async def execute(
        session: AsyncSession,
        redis: Redis,
        current_user_id: int,
        payload: CreateUserRequest,
        idempotency_key: str,
    ) -> UserResponseDetailed:
        payload_hash = _hash_payload(payload.model_dump(mode="json"))

        await acquire_idempotency_lock(
            session,
            redis,
            operation=IdempotencyOperation.USER_REGISTER,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        result = await UserService.register_user(session, current_user_id, payload)

        response = UserResponseDetailed.model_validate(result)

        await complete_idempotency_record(
            session,
            redis,
            operation=IdempotencyOperation.USER_REGISTER,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_201_CREATED,
            body=response.model_dump(mode="json"),
        )

        await session.commit()

        await session.commit()

        try:
            await mirror_complete_to_redis_after_commit(
                redis,
                operation=IdempotencyOperation.USER_REGISTER,
                actor_id=current_user_id,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                http_status=status.HTTP_201_CREATED,
                body=response.model_dump(mode="json"),
            )
        except RedisError as exc:
            logger.warning(
                "idempotency_redis_mirror_failed",
                operation=IdempotencyOperation.USER_REGISTER,
                actor_id=current_user_id,
                error=str(exc),
            )

        return response
