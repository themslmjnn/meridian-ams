from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from src.users.models.credentials import UserCredentials


class AuthRepository:
    @staticmethod
    async def get_credentials_by_username(
        session: AsyncSession,
        username: str,
    ) -> UserCredentials | None:
        result = await session.execute(
            select(UserCredentials)
            .where(UserCredentials.username == username)
            .options(
                selectinload(UserCredentials.login_lockout),
                selectinload(UserCredentials.identity),
            )
        )
        return result.scalar_one_or_none()
