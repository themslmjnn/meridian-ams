from fastapi import APIRouter, status

from src.core.dependencies import db_session_dependency, require_system_admin
from src.groups.schemas.system_admin import CreateGroup, GroupResponseAdminDetailed
from src.groups.services.system_admin import GroupServiceAdmin

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
