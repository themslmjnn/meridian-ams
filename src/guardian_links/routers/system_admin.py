import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, Request, Response, status

from src.core.dependencies import (
    db_session_dependency,
    redis_dependency,
    require_system_admin,
)
from src.core.idempotency.service import make_idempotency_key_dependency
from src.core.pagination import CursorPage
from src.guardian_links.schemas.system_admin import (
    CreateGuardianLink,
    GuardianLinkResponse,
    SearchGuardianLink,
)
from src.guardian_links.services.system_admin import GuardianLinkService
from src.guardian_links.use_cases.create_guardian_link import CreateGuardianLinkUseCase

router = APIRouter(
    prefix="/api/v1/admin/guardian-links",
    tags=["Guardian Links - System Admin"],
)


@router.post(
    "",
    response_model=GuardianLinkResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_guardian_link(
    request: Request,
    response: Response,
    db_session: db_session_dependency,
    redis: redis_dependency,
    current_user: require_system_admin,
    payload: CreateGuardianLink,
    idempotency_key: Annotated[str, Depends(make_idempotency_key_dependency())],
):
    return await CreateGuardianLinkUseCase.execute(
        db_session,
        redis,
        current_user.credentials_id,
        payload,
        idempotency_key,
    )


@router.delete(
    "/student/{student_public_id}/guardian/{guardian_public_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_guardian_link(
    db_session: db_session_dependency,
    current_user: require_system_admin,
    student_public_id: uuid.UUID,
    guardian_public_id: uuid.UUID,
):
    await GuardianLinkService.delete_guardian_link(
        db_session, current_user.credentials_id, student_public_id, guardian_public_id
    )


@router.get(
    "",
    response_model=CursorPage[GuardianLinkResponse],
    status_code=status.HTTP_200_OK,
)
async def get_guardian_links(
    db_session: db_session_dependency,
    _current_user: require_system_admin,
    filters: Annotated[SearchGuardianLink, Depends()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    next_cursor: Annotated[str | None, Query()] = None,
    prev_cursor: Annotated[str | None, Query()] = None,
):
    return await GuardianLinkService.get_guardian_links(
        db_session,
        filters=filters,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )
