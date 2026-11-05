import uuid

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.core.idempotency.models import IdempotencyRecord
from meridian_ams.core.idempotency.utils.enums import IdempotencyOperation


class IdempotencyRepository:
    @staticmethod
    async def delete_expired(
        db_session: AsyncSession,
        *,
        operation: IdempotencyOperation,
        actor_id: int,
        idempotency_key: uuid.UUID,
    ) -> None:
        query = delete(IdempotencyRecord).where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
            IdempotencyRecord.expires_at <= func.now(),
        )

        await db_session.execute(query)

    @staticmethod
    async def get_record(
        db_session: AsyncSession,
        *,
        operation: IdempotencyOperation,
        actor_id: int,
        idempotency_key: uuid.UUID,
    ):
        query = select(IdempotencyRecord).where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
            IdempotencyRecord.expires_at > func.now(),
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
