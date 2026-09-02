from __future__ import annotations

import uuid

from sqlalchemy import RowMapping, Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.models.session import UserSession
from src.users.utils.enums import AccountType, UserRole
from src.users.utils.schemas import LoadOptionsSchema


class UserCredentialsRepository:
    @staticmethod
    def _build_load_options(
        query: Select,
        load_options: LoadOptionsSchema,
    ) -> Select:
        """
        Apply joinedload options to a credentials query.

        Centralised here so every lookup method uses the same flag set
        consistently — no method has a different subset of flags.
        """
        if load_options.load_identity:
            query = query.options(joinedload(UserCredentials.identity))
        if load_options.load_sessions:
            query = query.options(joinedload(UserCredentials.sessions))
        if load_options.load_activation:
            query = query.options(joinedload(UserCredentials.activation))
        if load_options.load_login_lockout:
            query = query.options(joinedload(UserCredentials.login_lockout))
        if load_options.load_email_change:
            query = query.options(joinedload(UserCredentials.email_change))
        if load_options.load_password_reset:
            query = query.options(joinedload(UserCredentials.password_reset))

        return query

    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        credentials_id: int,
        **load_options: LoadOptionsSchema,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.id == credentials_id)
        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(
        session: AsyncSession,
        public_id: uuid.UUID,
        *,
        excluded_roles: frozenset[UserRole] | None = None,
        **load_options: LoadOptionsSchema,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.public_id == public_id)

        if excluded_roles:
            query = query.where(UserCredentials.role.not_in(excluded_roles))

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        session: AsyncSession,
        username: str,
        **load_options: LoadOptionsSchema,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.username == username)
        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_email(
        session: AsyncSession,
        email: str,
        *,
        account_type: AccountType | None = None,
        **load_options: LoadOptionsSchema,
    ) -> UserCredentials | None:
        """
        Look up credentials by email address.

        account_type should always be supplied when the caller knows it —
        student email is non-unique so omitting account_type on a student
        lookup may return an unexpected row.
        """
        query = select(UserCredentials).where(UserCredentials.email == email)

        if account_type is not None:
            query = query.where(UserCredentials.account_type == account_type)

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_personal_accounts_by_identity_id(
        session: AsyncSession,
        identity_id: int,
    ) -> UserCredentials | None:
        """
        Check whether a PERSONAL credentials row already exists for this identity.
        Used during guardian registration with existing_identity_id to prevent
        duplicate personal accounts for the same physical person.
        """
        query = select(UserCredentials).where(
            UserCredentials.identity_id == identity_id,
            UserCredentials.account_type == AccountType.PERSONAL,
        )

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def count_by_phone_and_account_type(
        session: AsyncSession,
        phone_number: str,
        account_type: AccountType,
        *,
        exclude_credentials_id: int | None = None,
    ) -> int:
        """
        Count credentials rows whose linked identity has this phone number,
        filtered by account type.

        Phone lives on UserIdentity so a join is required.
        """
        query = (
            select(func.count())
            .select_from(UserCredentials)
            .join(UserIdentity, UserCredentials.identity_id == UserIdentity.id)
            .where(
                UserIdentity.phone_number == phone_number,
                UserCredentials.account_type == account_type,
            )
        )

        if exclude_credentials_id is not None:
            query = query.where(UserCredentials.id != exclude_credentials_id)

        result = await session.execute(query)

        return result.scalar_one()

    @staticmethod
    async def count_by_email_and_account_type(
        session: AsyncSession,
        email: str,
        account_type: AccountType,
        *,
        exclude_credentials_id: int | None = None,
    ) -> int:
        """
        Count credentials rows with this email and account type.
        Only meaningful for students — staff/guardian uniqueness is enforced
        by the DB partial unique index.
        """
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

        result = await session.execute(query)

        return result.scalar_one()


class UserIdentityRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        identity_id: int,
    ) -> UserIdentity | None:
        query = select(UserIdentity).where(UserIdentity.id == identity_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def count_credentials(
        session: AsyncSession,
        identity_id: int,
    ) -> int:
        """
        Count how many credentials rows reference this identity.
        Used by the deletion worker to decide whether to also delete
        the identity after deleting the guardian's credentials.
        """
        query = (
            select(func.count())
            .select_from(UserCredentials)
            .where(UserCredentials.identity_id == identity_id)
        )

        result = await session.execute(query)

        return result.scalar_one()


class UserSessionRepository:
    @staticmethod
    async def get_by_id(
        session: AsyncSession,
        session_id: int,
    ) -> UserSession | None:
        query = select(UserSession).where(UserSession.id == session_id)

        result = await session.execute(query)

        return result.scalar_one_or_none()


class UserResponseRepository:
    """
    Queries that return flat RowMapping results for direct serialisation
    into response schemas. Kept separate from entity repositories to make
    the distinction between 'load an ORM object for mutation' and
    'fetch a flat read projection for a response' explicit.
    """

    @staticmethod
    async def get_registered_user_response(
        session: AsyncSession,
        public_id: uuid.UUID,
    ) -> RowMapping | None:
        result = await session.execute(
            select(
                UserCredentials.public_id,
                UserCredentials.username,
                UserCredentials.email,
                UserCredentials.role,
                UserCredentials.account_type,
                UserCredentials.status,
                UserCredentials.deletion_scheduled_for,
                UserCredentials.created_at,
                UserCredentials.updated_at,
                UserIdentity.firstname,
                UserIdentity.lastname,
                UserIdentity.middlename,
                UserIdentity.phone_number,
                UserIdentity.date_of_birth,
                UserIdentity.address,
            )
            .join(UserIdentity, UserCredentials.identity_id == UserIdentity.id)
            .where(UserCredentials.public_id == public_id)
        )

        return result.mappings().one_or_none()
