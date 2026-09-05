from datetime import datetime

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, joinedload

from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
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
    async def get_session_count(
        session: AsyncSession,
        credentials_id: int,
    ) -> int:
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
    async def evict_oldest_session(
        session: AsyncSession,
        credentials_id: int,
    ) -> None:
        # Find the session with the oldest last_active_at.
        # NULL last_active_at means never used — evict those first.
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
    async def delete_session(
        session: AsyncSession,
        user_session: UserSession,
    ) -> None:
        await session.delete(user_session)
        await session.flush()

    @staticmethod
    async def delete_all_sessions(
        session: AsyncSession,
        credentials_id: int,
    ) -> None:
        query = delete(UserSession).where(UserSession.credentials_id == credentials_id)

        await session.execute(query)
        await session.flush()

    @staticmethod
    async def get_session_ids(
        session: AsyncSession, credentials_id: int
    ) -> list[UserSession]:
        query = select(UserSession.id).where(
            UserSession.credentials_id == credentials_id
        )

        result = await session.execute(query)

        return result.scalars().all()

    @staticmethod
    async def invalidate_session_family(
        session: AsyncSession,
        user_session: UserSession,
    ) -> None:
        """
        Security violation — wipe all token state on this session.
        Bumps ATV so any in-flight access tokens are immediately rejected.
        """

        user_session.access_token_version += 1
        user_session.refresh_token_hash = None
        user_session.previous_refresh_token_hash = None
        user_session.refresh_token_family = None
        user_session.refresh_token_expires_at = None
        user_session.rotated_at = None

        await session.flush()

    @staticmethod
    async def get_session_by_id(
        session: AsyncSession, session_id: int
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.id == session_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_credentials_by_activation_token_hash(
        session: AsyncSession,
        activation_token_hash: str,
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
    async def claim_activation_token(
        session: AsyncSession,
        credentials_id: int,
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
    async def get_credentials_by_reset_token_hash(
        session: AsyncSession,
        token_hash: str,
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
    async def get_all_session_ids(
        session: AsyncSession,
        credentials_id: int,
    ) -> list[int]:
        query = select(UserSession.id).where(
            UserSession.credentials_id == credentials_id
        )

        result = await session.execute(query)

        return list(result.scalars().all())

    @staticmethod
    async def delete_password_reset_token(
        session: AsyncSession,
        credentials_id: int,
    ) -> None:
        query = delete(UserPasswordReset).where(
            UserPasswordReset.credentials_id == credentials_id
        )
        await session.execute(query)
        await session.flush()
