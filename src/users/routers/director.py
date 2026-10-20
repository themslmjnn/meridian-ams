import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from src.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_director,
)
from src.core.limiter import user_limiter
from src.core.pagination import CursorPage
from src.users.schemas.director import UserResponseDirectorDetailed
from src.users.schemas.system_admin import SearchUserBase
from src.users.services.director import UserServiceDirector
from src.users.utils.schemas import UserResponseBase

router = APIRouter(
    prefix="/api/v1/director/users",
    tags=["Users - Director"],
)


@router.get(
    "/staff",
    response_model=CursorPage[UserResponseBase],
    status_code=status.HTTP_200_OK,
)
@user_limiter.limit("30/minute")
async def get_staff(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    _current_user: require_director,
    filters: Annotated[SearchUserBase, Depends()],
    limit: int = Query(default=20, ge=1, le=100),
    next_cursor: str | None = Query(default=None),
    prev_cursor: str | None = Query(default=None),
):
    return await UserServiceDirector.get_staff(
        db_session,
        filters=filters,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )


@router.get(
    "/staff/{public_id}",
    response_model=UserResponseDirectorDetailed,
    status_code=status.HTTP_200_OK,
)
@user_limiter.limit("30/minute")
async def get_staff_by_public_id(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    _current_user: require_director,
    public_id: uuid.UUID,
):
    return await UserServiceDirector.get_staff_by_public_id(
        db_session, redis, public_id
    )
