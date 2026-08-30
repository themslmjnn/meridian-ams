from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.dependencies import CurrentUser, require_system_admin, session_dependency
from src.core.pagination import CursorPage
from src.emails.schemas import EmailResponseBase, SearchEmail
from src.emails.service import EmailService
from src.emails.utils.enums import EmailSortField
from src.utils.enums import OrderBy

router = APIRouter(
    prefix="/api/v1/admin/emails",
    tags=["Emails — System Admin"],
)


@router.get(
    "",
    response_model=CursorPage[EmailResponseBase],
    status_code=status.HTTP_200_OK,
)
async def get_emails(
    _: Annotated[CurrentUser, Depends(require_system_admin)],
    session: session_dependency,
    filters: Annotated[SearchEmail, Depends()],
    next_cursor: Annotated[str | None, Query()] = None,
    prev_cursor: Annotated[str | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    sort_by: Annotated[EmailSortField, Query()] = EmailSortField.CREATED_AT,
    order: Annotated[OrderBy, Query()] = OrderBy.DESC,
):
    return await EmailService.get_emails(
        session,
        filters=filters,
        limit=limit,
        sort_by=sort_by,
        order=order,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )
