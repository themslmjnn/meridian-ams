from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.utils.enums import AccountType


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
        query = select(func.count()).select_from(UserCredentials).where(
            UserCredentials.email == email,
            UserCredentials.account_type == account_type,
        )

        if exclude_credentials_id is not None:
            query = query.where(UserCredentials.id != exclude_credentials_id)

        result = await session.execute(query)
        
        return result.scalar_one()