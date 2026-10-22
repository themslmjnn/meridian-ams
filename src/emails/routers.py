from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Request, Response, status

from src.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_system_admin,
)
from src.core.limiter import user_limiter
from src.core.pagination import CursorPage
from src.emails.schemas import EmailResponseBase, EmailResponseDetailed, SearchEmail
from src.emails.service import EmailService

router = APIRouter(
    prefix="/api/v1/admin/emails",
    tags=["Emails — System Admin"],
)


@router.get(
    "",
    response_model=CursorPage[EmailResponseBase],
    status_code=status.HTTP_200_OK,
)
@user_limiter.limit("30/minute")
async def get_emails(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    _current_user: require_system_admin,
    filters: Annotated[SearchEmail, Depends()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    next_cursor: Annotated[str | None, Query()] = None,
    prev_cursor: Annotated[str | None, Query()] = None,
):
    return await EmailService.get_emails(
        db_session,
        filters=filters,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )


@router.get(
    "/{email_id}",
    response_model=EmailResponseDetailed,
    status_code=status.HTTP_200_OK,
)
@user_limiter.limit("30/minute")
async def get_email_by_id(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    _current_user: require_system_admin,
    email_id: Annotated[int, Path(ge=1)],
):
    return await EmailService.get_email_by_id(db_session, redis, email_id)


@router.post(
    "/{email_id}/retry",
    status_code=status.HTTP_204_NO_CONTENT,
)
@user_limiter.limit("10/minute")
async def retry_failed_email(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    _current_user: require_system_admin,
    email_id: Annotated[int, Path(ge=1)],
):
    await EmailService.retry_failed_email(db_session, email_id)
