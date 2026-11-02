from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.models.identity import UserIdentity
from meridian_ams.users.utils.enums import AccountType


class UserCredentialsRepository:
    @staticmethod
    async def get_by_id(
        db_session: AsyncSession, credentials_id: int
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.id == credentials_id)

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
