import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from src.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_system_admin,
)
from src.core.limiter import user_limiter
from src.core.pagination import CursorPage
from src.groups.schemas.system_admin import (
    CreateGroup,
    GroupResponseAdminDetailed,
    GroupResponseBase,
    SearchGroupAdmin,
    UpdateGroup,
)
from src.groups.services.system_admin import GroupServiceAdmin
from src.groups.utils.enums import GroupSortField
from src.utils.enums import OrderBy

router = APIRouter(
    prefix="/api/v1/admin/groups",
    tags=["Groups - System Admin"],
)


@router.post(
    "",
    response_model=GroupResponseAdminDetailed,
    status_code=status.HTTP_201_CREATED,
)
async def create_group(
    db_session: db_session_dependency,
    current_user: require_system_admin,
    payload: CreateGroup,
):
    return await GroupServiceAdmin.create_group(
        db_session, current_user.credentials_id, payload
    )


@router.patch(
    "/{public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def update_group(
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
    payload: UpdateGroup,
):
    await GroupServiceAdmin.update_group(
        db_session, redis, current_user.credentials_id, public_id, payload
    )


@router.patch(
    "/{public_id}/archive",
    status_code=status.HTTP_200_OK,
)
async def archive_group(
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
) -> dict:
    student_count = await GroupServiceAdmin.archive_group(
        db_session, redis, current_user.credentials_id, public_id
    )

    return {
        "message": "Group archived",
        "active_students_at_archive": student_count,
    }


@router.patch("/{public_id}/restore", status_code=status.HTTP_204_NO_CONTENT)
async def restore_group(
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_system_admin,
    public_id: uuid.UUID,
):
    await GroupServiceAdmin.restore_group(
        db_session, redis, current_user.credentials_id, public_id
    )


@router.get(
    "",
    response_model=list[GroupResponseBase],
    status_code=status.HTTP_200_OK,
)
@user_limiter.limit("30/minute")
async def get_groups(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    _current_user: require_system_admin,
    filters: Annotated[SearchGroupAdmin, Depends()],
    sort_by: GroupSortField = GroupSortField.ACADEMIC_YEAR,
    order: OrderBy = OrderBy.DESC,
):
    return await GroupServiceAdmin.get_groups(db_session, filters, sort_by, order)


@router.get(
    "/{public_id}",
    response_model=GroupResponseAdminDetailed,
    status_code=status.HTTP_200_OK,
)
async def get_group_by_id(
    db_session: db_session_dependency,
    _: require_system_admin,
    public_id: uuid.UUID,
):
    return await GroupServiceAdmin.get_group_by_public_id(db_session, public_id)
