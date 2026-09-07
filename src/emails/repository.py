from datetime import UTC, datetime

from sqlalchemy import Select, String, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage, paginate
from src.emails.models import Email
from src.emails.schemas import SearchEmail
from src.emails.utils.enums import EmailStatus


class EmailRepository:
    @staticmethod
    async def get_pending_batch(
        session: AsyncSession, *, limit: int = 20
    ) -> list[Email]:
        """
        Fetch a batch of emails ready to send.
        Conditions:
          - status = PENDING
          - scheduled_for <= now()
          - retry_count < max_retries (skip permanently exhausted rows)
        Ordered oldest-first so earlier queued emails go out first.
        """

        result = await session.execute(
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING,
                Email.retry_count < Email.max_retries,
            )
            .order_by(Email.id.asc())
            .limit(limit)
        )

        return list(result.scalars().all())

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
        """Reset a FAILED email back to PENDING for manual retry."""
        record.status = EmailStatus.PENDING
        record.retry_count = 0
        record.last_error = None

    @staticmethod
    def apply_filters(base_query: Select, filters: SearchEmail | None) -> Select:
        if filters is None:
            return base_query

        if filters.status is not None:
            base_query = base_query.where(Email.status == filters.status)
        if filters.email_type is not None:
            base_query = base_query.where(Email.email_type == filters.email_type)
        if filters.triggered_by is not None:
            base_query = base_query.where(Email.triggered_by == filters.triggered_by)
        if filters.recipient_email is not None:
            base_query = base_query.where(
                Email.recipient_email.cast(String).ilike(f"%{filters.recipient_email}%")
            )

        return base_query

    @staticmethod
    async def get_emails(
        session: AsyncSession,
        *,
        filters: SearchEmail | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage:
        query = select(Email)
        query = EmailRepository.apply_filters(query, filters)

        return await paginate(
            session,
            query,
            model=Email,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

    @staticmethod
    async def get_by_id(session: AsyncSession, email_id: int) -> Email | None:
        query = select(Email).where(Email.id == email_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_triggered_by(
        session: AsyncSession, credentials_id: int
    ) -> list[Email]:
        query = select(Email).where(Email.triggered_by == credentials_id)

        result = await session.execute(query)

        return result.scalars().all()
