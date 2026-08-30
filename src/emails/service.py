from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage
from src.emails.repository import EmailRepository
from src.emails.schemas import EmailResponseBase, SearchEmail
from src.emails.utils.enums import EmailSortField
from src.utils.enums import OrderBy


class EmailService:
    @staticmethod
    async def get_emails(
        session: AsyncSession,
        *,
        filters: SearchEmail | None = None,
        limit: int = 20,
        sort_by: str = EmailSortField.CREATED_AT,
        order: str = OrderBy.DESC,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
    ) -> CursorPage[EmailResponseBase]:
        emails = await EmailRepository.get_emails(
            session,
            filters=filters,
            limit=limit,
            sort_by=sort_by,
            order=order,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

        return CursorPage[EmailResponseBase](
            items=[EmailResponseBase.model_validate(item) for item in emails.items],
            next_cursor=emails.next_cursor,
            prev_cursor=emails.prev_cursor,
            limit=emails.limit,
        )
