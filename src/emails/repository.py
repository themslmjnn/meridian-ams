from datetime import UTC, datetime

from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage, paginate
from src.emails.models import Email
from src.emails.schemas import SearchEmail
from src.emails.utils.enums import EmailStatus


class EmailRepository:
    @staticmethod
    async def get_pending_batch(
        db_session: AsyncSession, *, limit: int = 20
    ) -> list[Email]:
        query = (
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING,
                Email.retry_count < Email.max_retries,
            )
            .order_by(Email.id.asc())
            .limit(limit)
        )

        result = await db_session.execute(query)

        return result.scalars().all()

    @staticmethod
    async def mark_sent(record: Email) -> None:
        record.status = EmailStatus.SENT
        record.sent_at = datetime.now(UTC)

    @staticmethod
    async def mark_failed_attempt(record: Email, error: str) -> None:
        record.retry_count += 1
        record.last_error = error[:500]

        if record.retry_count >= record.max_retries:
            record.status = EmailStatus.FAILED

    @staticmethod
    async def reset_for_retry(record: Email) -> None:
        record.status = EmailStatus.PENDING
        record.retry_count = 0
        record.last_error = None

    @staticmethod
    def _apply_filters(base_query: Select, filters: SearchEmail | None) -> Select:
        if filters is not None:
            if filters.status:
                base_query = base_query.where(Email.status == filters.status)

            if filters.email_type:
                base_query = base_query.where(Email.email_type == filters.email_type)

            if filters.triggered_by:
                base_query = base_query.where(
                    Email.triggered_by == filters.triggered_by
                )

            if filters.recipient_email:
                base_query = base_query.where(
                    Email.recipient_email.ilike(f"%{filters.recipient_email}%")
                )

        return base_query

    @staticmethod
    async def get_emails(
        db_session: AsyncSession,
        *,
        filters: SearchEmail | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage:
        query = select(Email)
        query = EmailRepository._apply_filters(query, filters)

        return await paginate(
            db_session,
            query,
            model=Email,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

    @staticmethod
    async def get_by_id(db_session: AsyncSession, email_id: int) -> Email | None:
        query = select(Email).where(Email.id == email_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_triggered_by(
        db_session: AsyncSession, credentials_id: int
    ) -> list[Email]:
        query = select(Email).where(Email.triggered_by == credentials_id)

        result = await db_session.execute(query)

        return result.scalars().all()
