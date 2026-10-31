from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession


async def get_db_session(request: Request) -> AsyncIterator[AsyncSession]:
    async with request.app.state.async_session_factory() as db_session:
        yield db_session

db_session_dependency = Annotated[AsyncSession, Depends(get_db_session)]