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
from src.guardian_links.schemas.system_admin import (
    CreateGuardianLink,
    GuardianLinkResponse,
)
from src.guardian_links.services.system_admin import GuardianLinkService

logger = structlog.get_logger(__name__)


class CreateGuardianLinkUseCase:
    """Coordinates idempotency and guardian link creation in a single transaction."""

    @staticmethod
    async def execute(
        db_session: AsyncSession,
        redis: Redis,
        actor_id: int,
        payload: CreateGuardianLink,
        idempotency_key: str,
    ) -> GuardianLinkResponse:
        payload_hash = hash_payload(payload.model_dump(mode="json"))

        await acquire_idempotency_lock(
            db_session,
            redis,
            actor_id=actor_id,
            operation=IdempotencyOperation.CREATE_GUARDIAN_LINK,
            idempotency_key=idempotency_key,
            payload_hash=payload_hash,
        )

        result = await GuardianLinkService.create_guardian_link(
            db_session, actor_id, payload
        )

        response = GuardianLinkResponse.model_validate(result)

        await complete_idempotency_record(
            db_session,
            actor_id=actor_id,
            operation=IdempotencyOperation.CREATE_GUARDIAN_LINK,
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
                operation=IdempotencyOperation.CREATE_GUARDIAN_LINK,
                idempotency_key=idempotency_key,
                payload_hash=payload_hash,
                http_status=status.HTTP_201_CREATED,
                body=response.model_dump(mode="json"),
            )

        except RedisError as exc:
            logger.warning(
                "idempotency_redis_mirror_failed",
                actor_id=actor_id,
                operation=IdempotencyOperation.CREATE_GUARDIAN_LINK,
                error=str(exc),
            )

        return response
