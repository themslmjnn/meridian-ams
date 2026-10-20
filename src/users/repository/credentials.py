from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy import Select, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload, selectinload

from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.schemas import LoadOptionsSchema


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

            if load_options.load_email_change:
                query = query.options(joinedload(UserCredentials.email_change))

            if load_options.load_password_reset:
                query = query.options(joinedload(UserCredentials.password_reset))

        return query

    @staticmethod
    async def get_by_id(
        db_session: AsyncSession,
        credentials_id: int,
        *,
        account_type: AccountType | None = None,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.id == credentials_id)

        if account_type is not None:
            query = query.where(UserCredentials.account_type == account_type)

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_public_id(
        db_session: AsyncSession,
        public_id: uuid.UUID,
        *,
        account_type: AccountType | None = None,
        allowed_roles: frozenset[UserRole] | None = None,
        excluded_roles: frozenset[UserRole] | None = None,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.public_id == public_id)

        if account_type is not None:
            query = query.where(UserCredentials.account_type == account_type)

        if allowed_roles is not None:
            query = query.where(UserCredentials.role.in_(allowed_roles))

        if excluded_roles is not None:
            query = query.where(UserCredentials.role.not_in(excluded_roles))

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        db_session: AsyncSession,
        username: str,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.username == username)
        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

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

    @staticmethod
    async def count_credentials(db_session: AsyncSession, identity_id: int) -> int:
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

        result = await db_session.execute(query)

        return result.scalar_one()

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
    async def get_due_for_deletion(
        db_session: AsyncSession, limit: int = 50
    ) -> list[int]:
        """
        Returns a batch of credentials IDs due for hard deletion.
        Returns IDs only — the worker re-verifies each row individually
        via get_credentials_if_due before acting on it.
        """

        query = (
            select(UserCredentials.id)
            .where(
                UserCredentials.account_type == AccountType.PERSONAL,
                UserCredentials.status == UserStatus.PENDING_DELETION,
                UserCredentials.deletion_scheduled_for <= datetime.now(UTC),
            )
            .limit(limit)
        )

        result = await db_session.execute(query)

        return list(result.scalars().all())

    @staticmethod
    async def get_credentials_if_due(
        db_session: AsyncSession, credentials_id: int
    ) -> UserCredentials | None:
        """
        Re-verify a single row is still due for deletion before acting on it.
        Guards against the window between batch fetch and individual processing
        where an admin may have cancelled the deletion.
        Returns UserCredentials | None — never bool (SMS Lite bug fixed by design).
        """

        query = select(UserCredentials).where(
            UserCredentials.id == credentials_id,
            UserCredentials.account_type == AccountType.PERSONAL,
            UserCredentials.status == UserStatus.PENDING_DELETION,
            UserCredentials.deletion_scheduled_for <= datetime.now(UTC),
        )

        result = await db_session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def reactivate_pending_deletion_user(
        db_session: AsyncSession,
        public_id: uuid.UUID,
        pre_transition_status: UserRole,
    ) -> bool:
        query = (
            update(UserCredentials)
            .where(
                UserCredentials.public_id == public_id,
                UserCredentials.account_type == AccountType.PERSONAL,
                UserCredentials.status == UserStatus.PENDING_DELETION,
            )
            .values(
                status=pre_transition_status,
                deletion_scheduled_for=None,
            )
        )

        result = await db_session.execute(query)

        return result.rowcount > 0
