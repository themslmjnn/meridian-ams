from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.idempotency.models import IdempotencyRecord
from src.core.idempotency.utils.enums import IdempotencyStatus


class IdempotencyRepository:
    @staticmethod
    async def get_record(
        session: AsyncSession,
        *,
        operation: str,
        actor_id: int,
        idempotency_key: str,
    ) -> IdempotencyRecord | None:
        query = select(IdempotencyRecord).where(
            IdempotencyRecord.operation == operation,
            IdempotencyRecord.actor_id == actor_id,
            IdempotencyRecord.key == idempotency_key,
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def update_record(
        session: AsyncSession,
        operation: str,
        actor_id: int,
        idempotency_key: str,
        payload_hash: str,
        http_status: int,
        body: dict | list | str | None,
    ) -> int:
        query = (
            update(IdempotencyRecord)
            .where(
                IdempotencyRecord.operation == operation,
                IdempotencyRecord.actor_id == actor_id,
                IdempotencyRecord.key == idempotency_key,
                IdempotencyRecord.status == IdempotencyStatus.PROCESSING,
                IdempotencyRecord.request_hash == payload_hash,
            )
            .values(
                status=IdempotencyStatus.COMPLETE,
                http_status=http_status,
                response_body=body,
            )
        )

        result = await session.execute(query)

        return result.rowcount
