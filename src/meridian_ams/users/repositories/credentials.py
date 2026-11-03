import uuid

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.models.identity import UserIdentity
from meridian_ams.users.utils.enums import AccountType
from meridian_ams.users.utils.schemas import LoadOptionsSchema


class UserCredentialsRepository:
    @staticmethod
    def _build_load_options(
        query: Select, load_options: LoadOptionsSchema | None = None
    ) -> Select:
        """
        Apply joinedload options to a credentials query.

        Centralised here so every lookup method uses the same flag set
        consistently — no method has a different subset of flags.
        """

        if load_options is not None:
            if load_options.load_identity:
                query = query.options(joinedload(UserCredentials.identity))

            if load_options.load_sessions:
                query = query.options(selectinload(UserCredentials.sessions))

            if load_options.load_activation:
                query = query.options(joinedload(UserCredentials.activation))

            if load_options.load_login_lockout:
                query = query.options(joinedload(UserCredentials.login_lockout))

        return query

    @staticmethod
    async def get_by_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.id == credentials_id)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(
        db_session: AsyncSession,
        public_id: uuid.UUID,
        *,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.public_id == public_id)

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        db_session: AsyncSession,
        username: str,
        *,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.username == username)
        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_phone_and_account_type(
        db_session: AsyncSession,
        phone_number: str,
        account_type: AccountType,
        *,
        exclude_credentials_id: int | None = None,
    ) -> int:
        account_type_condition = (
            frozenset({AccountType.STUDENT}),
            frozenset({AccountType.WORK, AccountType.PERSONAL}),
        )[account_type != AccountType.STUDENT]

        query = (
            select(func.count())
            .select_from(UserCredentials)
            .join(UserIdentity, UserCredentials.identity_id == UserIdentity.id)
            .where(
                UserIdentity.phone_number == phone_number,
                UserCredentials.account_type.in_(account_type_condition),
            )
        )

        if exclude_credentials_id is not None:
            query = query.where(UserCredentials.id != exclude_credentials_id)

        result = await db_session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def count_by_email_and_account_type(
        db_session: AsyncSession,
        email: str,
        account_type: AccountType,
        *,
        exclude_credentials_id: int | None = None,
    ) -> int:
        query = (
            select(func.count())
            .select_from(UserCredentials)
            .where(
                UserCredentials.email == email,
                UserCredentials.account_type == account_type,
            )
        )

        if exclude_credentials_id is not None:
            query = query.where(UserCredentials.id != exclude_credentials_id)

        result = await db_session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def get_personal_accounts_by_identity_id(
        db_session: AsyncSession, identity_id: int
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(
            UserCredentials.identity_id == identity_id,
            UserCredentials.account_type == AccountType.PERSONAL,
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()
