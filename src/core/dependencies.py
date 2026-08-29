from collections.abc import AsyncGenerator
from typing import Annotated

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.connection import session_factory


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with session_factory() as session:
        try:
            yield session

        except Exception:
            await session.rollback()

            raise


session_dependency = Annotated[AsyncSession, Depends(get_session)]
