from __future__ import annotations

import structlog
from fastapi import Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.core.idempotency.service import (
    acquire_idempotency_lock,
    hash_payload,
    mirror_complete_to_redis,
    store_idempotency_record,
)
from meridian_ams.core.idempotency.utils.enums import IdempotencyOperation
from meridian_ams.users.schemas.system_admin import (
    CreateUserRequest,
    UserResponseDetailedAdmin,
)
from meridian_ams.users.services.system_admin import UserServiceAdmin

logger = structlog.get_logger(__name__)


class RegisterUserUseCase:
    @staticmethod
    async def execute(
        request: Request,
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        payload: CreateUserRequest,
        idempotency_key: str,
    ) -> UserResponseDetailedAdmin:
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

        result = await UserServiceAdmin.register_user(db_session, actor_id, payload)

        response = UserResponseDetailedAdmin.model_validate(result)

        body = response.model_dump(mode="json")

        expires_at = await store_idempotency_record(
            db_session,
            actor_id=actor_id,
            operation=IdempotencyOperation.REGISTER_USER,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_201_CREATED,
            body=body,
        )

        await db_session.commit()

        await mirror_complete_to_redis(
            redis,
            actor_id=actor_id,
            operation=IdempotencyOperation.REGISTER_USER,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_201_CREATED,
            body=body,
            expires_at=expires_at,
        )

        return response
