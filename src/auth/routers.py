from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status
from fastapi.security import OAuth2PasswordRequestForm
from redis.asyncio import Redis

from src.auth.schemas import LoginResponse
from src.auth.service import AuthService
from src.core.caching import get_redis
from src.core.dependencies import current_user_dependency, session_dependency

router = APIRouter(
    prefix="/auth",
    tags=["Auth"],
)

redis_dependency = Annotated[Redis, Depends(get_redis)]


@router.post("/login", response_model=LoginResponse, status_code=status.HTTP_200_OK)
async def login(
    request: Request,
    response: Response,
    session: session_dependency,
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
):
    return await AuthService.login(
        session=session,
        request=request,
        response=response,
        form_data=form_data,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(
    response: Response,
    db: session_dependency,
    redis: redis_dependency,
    current_user: current_user_dependency,
) -> None:
    await AuthService.logout(
        db=db,
        redis=redis,
        response=response,
        current_user=current_user,
    )
