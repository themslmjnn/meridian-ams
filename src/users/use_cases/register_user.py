from fastapi import status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency import (
    _hash_payload,
    acquire_idempotency_lock,
    complete_idempotency_record,
)
from src.users.schemas.system_admin import CreateUserRequest, UserResponseDetailed
from src.users.services.system_admin import UserService
from src.utils.enums import IdempotencyOperation


class RegisterUserUseCase:
    """
    Coordinates idempotency + business operation for user registration.

    Responsibilities:
    - Idempotency: acquire lock, replay if duplicate, complete on success
    - Business: delegate to UserServiceAdmin.register_user
    - Transaction boundary: business operation commits, then idempotency completes

    The router handles: auth, rate limiting, request parsing, response serialisation.
    UserServiceAdmin handles: domain rules, DB writes, email queuing.
    This class handles: the coordination between them.
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
            redis,
            operation=IdempotencyOperation.USER_REGISTER,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        result = await UserService.register_user(session, current_user_id, payload)

        response = UserResponseDetailed.model_validate(result)

        await complete_idempotency_record(
            redis,
            operation=IdempotencyOperation.USER_REGISTER,
            actor_id=current_user_id,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
            http_status=status.HTTP_201_CREATED,
            body=response.model_dump(mode="json"),
        )

        return response
