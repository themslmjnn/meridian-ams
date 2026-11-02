from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, RowMapping, Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from meridian_ams.users.models.credentials import UserCredentials
from meridian_ams.users.models.identity import UserIdentity

_USER_MAPPED_COLUMNS_DETAILED: tuple[ColumnElement[Any], ...] = (
    UserCredentials.public_id,
    UserCredentials.username,
    UserCredentials.email,
    UserCredentials.role,
    UserCredentials.account_type,
    UserCredentials.status,
    UserCredentials.created_at,
    UserCredentials.updated_at,
    UserIdentity.first_name,
    UserIdentity.last_name,
    UserIdentity.middle_name,
    UserIdentity.phone_number,
    UserIdentity.date_of_birth,
    UserIdentity.address,
)


class UserRepositoryBase:
    @staticmethod
    def get_base_join(mapped_columns: Sequence[ColumnElement[Any]]) -> Select:
        query = select(*mapped_columns).join(
            UserIdentity, UserCredentials.identity_id == UserIdentity.id
        )

        return query


class UserResponseRepository:
    """
    Queries that return flat RowMapping results for direct serialisation
    into response schemas. Kept separate from entity repositories to make
    the distinction between 'load an ORM object for mutation' and
    'fetch a flat read projection for a response' explicit.
    """

    @staticmethod
    async def get_registered_user_response(
        db_session: AsyncSession, public_id: uuid.UUID
    ) -> RowMapping | None:
        base_join = UserRepositoryBase.get_base_join(_USER_MAPPED_COLUMNS_DETAILED)

        query = base_join.where(UserCredentials.public_id == public_id)

        result = await db_session.execute(query)

        return result.mappings().one_or_none()
