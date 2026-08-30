from datetime import UTC, datetime

from sqlalchemy import String, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage, paginate
from src.emails.models import Email
from src.emails.schemas import CreateEmail, EmailFilters
from src.users.utils.enums import EmailStatus


class EmailRepository:
    @staticmethod
    async def queue(session: AsyncSession, data: CreateEmail) -> Email:
        """
        Insert a pending email row. Never commits — caller owns the transaction.
        Always called within the same transaction as the triggering auth operation.
        """
        email = Email(
            recipient_email=str(data.recipient_email),
            subject=data.subject,
            body_html=data.body_html,
            email_type=data.email_type,
            triggered_by=data.triggered_by,
            **({"scheduled_for": data.scheduled_for} if data.scheduled_for else {}),
        )

        session.add(email)
        return email

    # ---------------------------------------------------------------------------
    # Worker queries
    # ---------------------------------------------------------------------------

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
        now = datetime.now(UTC)

        result = await session.execute(
            select(Email)
            .where(
                Email.status == EmailStatus.PENDING,
                Email.scheduled_for <= now,
                Email.retry_count < Email.max_retries,
            )
            .order_by(Email.scheduled_for.asc(), Email.id.asc())
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
    async def get_list(
        session: AsyncSession,
        *,
        filters: EmailFilters | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage:
        query = select(Email)
        query = EmailRepository._apply_filters(query, filters)

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
        result = await session.execute(select(Email).where(Email.id == email_id))

        return result.scalar_one_or_none()

    @staticmethod
    async def reset_for_retry(record: Email) -> None:
        """Reset a FAILED email back to PENDING for manual retry."""
        record.status = EmailStatus.PENDING
        record.retry_count = 0
        record.last_error = None

    @staticmethod
    def _apply_filters(query, filters: EmailFilters | None):
        if filters is None:
            return query
        if filters.status is not None:
            query = query.where(Email.status == filters.status)
        if filters.email_type is not None:
            query = query.where(Email.email_type == filters.email_type)
        if filters.triggered_by is not None:
            query = query.where(Email.triggered_by == filters.triggered_by)
        if filters.recipient_email is not None:
            query = query.where(
                Email.recipient_email.cast(String).ilike(f"%{filters.recipient_email}%")
            )

        return query
