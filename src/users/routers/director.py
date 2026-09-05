import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request

from src.core.dependencies import require_director, session_dependency
from src.core.pagination import CursorPage
from src.users.schemas.director import UserResponseDirectorDetailed
from src.users.schemas.system_admin import (
    SearchUserBase,
)
from src.users.services.director import UserServiceDirector

router = APIRouter(
    prefix="/api/v1/director/users",
    tags=["Users - Director"],
)


@router.get(
    "/staff",
    response_model=CursorPage[UserResponseDirectorDetailed],
)
async def get_staff(
    session: session_dependency,
    _current_user: require_director,
    filters: Annotated[SearchUserBase, Depends()],
    limit: int = Query(default=20, ge=1, le=100),
    next_cursor: str | None = Query(default=None),
    prev_cursor: str | None = Query(default=None),
):
    return await UserServiceDirector.get_staff(
        session,
        filters=filters,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )


@router.get(
    "/staff/{public_id}",
    response_model=UserResponseDirectorDetailed,
)
async def get_staff_by_public_id(
    request: Request,
    session: session_dependency,
    _current_user: require_director,
    public_id: uuid.UUID,
):
    return await UserServiceDirector.get_staff_by_public_id(request, session, public_id)
