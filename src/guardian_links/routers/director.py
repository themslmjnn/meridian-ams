import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status

from src.core.dependencies import db_session_dependency, require_director
from src.core.pagination import CursorPage
from src.guardian_links.schemas.director import GuardianLinkResponseDirector
from src.guardian_links.schemas.system_admin import SearchGuardianLink
from src.guardian_links.services.director import GuardianLinkServiceDirector

router = APIRouter(
    prefix="/api/v1/director/guardian-links",
    tags=["Guardian Links - Director"],
)


@router.get(
    "",
    response_model=CursorPage[GuardianLinkResponseDirector],
    status_code=status.HTTP_200_OK,
)
async def get_guardian_links(
    db_session: db_session_dependency,
    _current_user: require_director,
    filters: Annotated[SearchGuardianLink, Depends()],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    next_cursor: Annotated[str | None, Query()] = None,
    prev_cursor: Annotated[str | None, Query()] = None,
):
    return await GuardianLinkServiceDirector.get_guardian_links(
        db_session,
        filters=filters,
        limit=limit,
        next_cursor=next_cursor,
        prev_cursor=prev_cursor,
    )


@router.get(
    "/student/{student_public_id}",
    response_model=list[GuardianLinkResponseDirector],
    status_code=status.HTTP_200_OK,
)
async def get_links_by_student(
    db_session: db_session_dependency,
    _current_user: require_director,
    student_public_id: uuid.UUID,
):
    return await GuardianLinkServiceDirector.get_links_by_student(
        db_session, student_public_id
    )
