from sqlalchemy.ext.asyncio import AsyncSession

from src.core.caching import get_cache, set_cache
from src.core.pagination import CursorPage
from src.emails.repository import EmailRepository
from src.emails.schemas import EmailResponseBase, EmailResponseDetailed, SearchEmail
from src.emails.utils.exceptions import EmailNotFoundError
from src.utils.cache_keys import EmailCacheKey


class EmailService:
    @staticmethod
    async def get_emails(
        session: AsyncSession,
        *,
        filters: SearchEmail | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[EmailResponseBase]:
        emails = await EmailRepository.get_emails(
            session,
            filters=filters,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return CursorPage[EmailResponseBase](
            items=[EmailResponseBase.model_validate(item) for item in emails.items],
            next_cursor=emails.next_cursor,
            prev_cursor=emails.prev_cursor,
            limit=emails.limit,
        )

    @staticmethod
    async def get_email_by_id(
        session: AsyncSession,
        email_id: int,
    ) -> EmailResponseDetailed:
        cache_key = EmailCacheKey.email_detail_key(email_id)
        cached_data = await get_cache(cache_key)

        if cached_data is not None:
            return EmailResponseDetailed.model_validate(cached_data)

        email = await EmailRepository.get_email_by_id(session, email_id)
        if email is None:
            raise EmailNotFoundError()

        response = EmailResponseDetailed.model_validate(email)

        await set_cache(cache_key, response.model_dump(mode="json"), 900)

        return response

    @staticmethod
    async def retry_failed_email(
        session: AsyncSession,
        email_id: int,
    ) -> None:
        failed_email = await EmailRepository.get_email_by_id(session, email_id)
        if failed_email is None:
            raise EmailNotFoundError()

        await EmailRepository.reset_for_retry(failed_email)

        await session.commit()
