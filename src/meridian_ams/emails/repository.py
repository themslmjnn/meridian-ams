from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.emails.enums import EmailStatus
from meridian_ams.emails.models import Email

RETRY_DELAY = timedelta(minutes=2)


class EmailRepository:
    @staticmethod
    async def get_pending_batch(
        db_session: AsyncSession, *, limit: int = 20
    ) -> list[Email]:
        query = (
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING,
                Email.scheduled_for <= func.now(),
            )
            .order_by(Email.id.asc())
            .limit(limit)
        )

        result = await db_session.execute(query)

        return result.scalars().all()

    @staticmethod
    def mark_sent(record: Email) -> None:
        record.status = EmailStatus.SENT
        record.sent_at = datetime.now(UTC)

    @staticmethod
    def mark_failed_attempt(record: Email, error: str) -> None:
        record.retry_count += 1
        record.last_error = error[:500]

        if record.retry_count >= record.max_retries:
            record.status = EmailStatus.FAILED
        else:
            record.scheduled_for = datetime.now(UTC) + RETRY_DELAY * record.retry_count
