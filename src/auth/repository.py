from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.models.login_lockout import UserLoginLockout
from src.users.models.password_reset import UserPasswordReset
from src.users.models.session import UserSession


class AuthRepository:
    @staticmethod
    async def get_session_by_device_id(
        session: AsyncSession,
        credentials_id: int,
        device_id: str,
    ) -> UserSession | None:
        query = select(UserSession).where(
            UserSession.credentials_id == credentials_id,
            UserSession.device_id == device_id,
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_session_count(session: AsyncSession, credentials_id: int) -> int:
        query = (
            select(func.count())
            .select_from(UserSession)
            .where(
                UserSession.credentials_id == credentials_id,
            )
        )

        result = await session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def get_session_ids(session: AsyncSession, credentials_id: int) -> list[int]:
        query = select(UserSession.id).where(
            UserSession.credentials_id == credentials_id
        )

        result = await session.execute(query)

        return result.scalars().all()

    @staticmethod
    async def evict_oldest_session(session: AsyncSession, credentials_id: int) -> None:
        query = (
            select(UserSession)
            .where(UserSession.credentials_id == credentials_id)
            .order_by(
                UserSession.last_active_at.asc().nulls_first(),
                UserSession.created_at.asc(),
            )
            .limit(1)
        )

        result = await session.execute(query)

        oldest = result.scalar_one_or_none()

        if oldest is not None:
            await session.delete(oldest)
            await session.flush()

    @staticmethod
    async def delete_all_sessions(session: AsyncSession, credentials_id: int) -> None:
        query = delete(UserSession).where(UserSession.credentials_id == credentials_id)

        await session.execute(query)

        await session.flush()

    @staticmethod
    async def get_credentials_by_activation_token_hash(
        session: AsyncSession, activation_token_hash: str
    ) -> UserCredentials | None:
        query = (
            select(UserCredentials)
            .join(
                UserActivation,
                UserActivation.credentials_id == UserCredentials.id,
            )
            .where(UserActivation.activation_token_hash == activation_token_hash)
            .options(
                joinedload(UserCredentials.activation),
            )
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_credentials_by_reset_password_token_hash(
        session: AsyncSession, token_hash: str
    ) -> UserCredentials | None:
        query = (
            select(UserCredentials)
            .join(
                UserPasswordReset,
                UserPasswordReset.credentials_id == UserCredentials.id,
            )
            .where(UserPasswordReset.reset_password_token_hash == token_hash)
            .options(
                joinedload(UserCredentials.password_reset),
                joinedload(UserCredentials.login_lockout),
            )
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def delete_reset_password_record(
        session: AsyncSession, credentials_id: int
    ) -> None:
        query = delete(UserPasswordReset).where(
            UserPasswordReset.credentials_id == credentials_id
        )

        await session.execute(query)

        await session.flush()

    @staticmethod
    async def claim_activation_token(
        session: AsyncSession, credentials_id: int
    ) -> bool:
        """
        Atomically delete the UserActivation row using DELETE ... RETURNING.
        Returns True if the row was claimed, False if another request got there first.
        """

        query = (
            delete(UserActivation)
            .where(UserActivation.credentials_id == credentials_id)
            .returning(UserActivation.id)
        )

        result = await session.execute(query)

        await session.flush()

        return result.scalar_one_or_none() is not None

    @staticmethod
    async def get_login_lockout_by_credentials_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserLoginLockout:
        query = (
            select(UserLoginLockout)
            .where(UserLoginLockout.credentials_id == credentials_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )

        result = await db_session.execute(query)

        return result.scalar_one()
