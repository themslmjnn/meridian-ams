import uuid

from sqlalchemy import RowMapping, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.utils.enums import AccountType


class UserRepositoryBase:
    @staticmethod
    async def get_registered_user_response(
        session: AsyncSession,
        public_id: uuid.UUID,
    ) -> RowMapping | None:
        query = (
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

        result = await session.execute(query)

        return result.mappings().one_or_none()


class UserCredentialsRepository:
    @staticmethod
    async def count_by_phone_and_account_type(
        session: AsyncSession,
        phone_number: str,
        account_type: AccountType,
        *,
        exclude_credentials_id: int | None = None,
    ) -> int:
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
    async def get_user_identity_by_id(
        session: AsyncSession, user_identity_id: int
    ) -> UserIdentity:
        query = select(UserIdentity).where(UserIdentity.id == user_identity_id)

        result = await session.execute(query)

        return result.scalars()
