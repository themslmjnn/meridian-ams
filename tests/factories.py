from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.core.idempotency.models import IdempotencyRecord
from meridian_ams.core.idempotency.utils.enums import IdempotencyStatus


async def make_idempotency_record(
    db_test_session: AsyncSession,
    *,
    actor_id: int,
    operation: str,
    key: str,
    status: IdempotencyStatus,
    request_hash: str,
    http_status: int | None = None,
    response_body: dict | None = None,
) -> IdempotencyRecord:
    record = IdempotencyRecord(
        key=key,
        operation=operation,
        actor_id=actor_id,
        request_hash=request_hash,
        status=status,
        http_status=http_status,
        response_body=response_body,
        expires_at=datetime.now(UTC) + timedelta(hours=24),
    )

    db_test_session.add(record)
    await db_test_session.flush()

    return record
