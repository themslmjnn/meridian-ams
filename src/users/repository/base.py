from __future__ import annotations

import uuid
from collections.abc import Sequence
from typing import Any

from sqlalchemy import ColumnElement, RowMapping, Select, asc, desc, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.pagination import CursorPage, decode_cursor, encode_cursor
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.schemas.system_admin import SearchUserBase
from src.users.utils.enums import UserRole

_USER_MAPPED_COLUMNS: tuple[ColumnElement[Any], ...] = (
    UserIdentity.firstname,
    UserIdentity.lastname,
    UserIdentity.middlename,
    UserIdentity.phone_number,
    UserCredentials.role,
)

_USER_MAPPED_COLUMNS_DETAILED: tuple[ColumnElement[Any], ...] = (
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


class UserRepositoryBase:
    @staticmethod
    def get_base_join(mapped_columns: Sequence[ColumnElement[Any]]) -> Select:
        query = select(*mapped_columns).join(
            UserIdentity, UserCredentials.identity_id == UserIdentity.id
        )

        return query

    @staticmethod
    def _apply_filters(base_query: Select, filters: SearchUserBase | None) -> Select:
        if filters is not None:
            if filters.firstname:
                base_query = base_query.where(
                    UserIdentity.firstname.ilike(f"%{filters.firstname}%")
                )

            if filters.lastname:
                base_query = base_query.where(
                    UserIdentity.lastname.ilike(f"%{filters.lastname}%")
                )

            if filters.phone_number:
                base_query = base_query.where(
                    UserIdentity.phone_number.ilike(f"%{filters.phone_number}%")
                )

            if filters.email:
                base_query = base_query.where(
                    UserCredentials.email.ilike(f"%{filters.email}%")
                )

            if filters.status:
                base_query = base_query.where(UserCredentials.status == filters.status)

        return base_query

    @staticmethod
    async def _paginate_mapped(
        session: AsyncSession,
        query: Select,
        *,
        limit: int,
        next_cursor: str | None,
        prev_cursor: str | None,
    ) -> CursorPage:
        """
        Cursor-based pagination for flat RowMapping queries (joined projections).

        Mirrors the logic in core/pagination.py but uses mappings() instead of
        scalars() since the query selects individual columns across two tables
        rather than a single ORM model.
        """

        limit = max(1, min(limit, 100))
        fetch = limit + 1

        query = query.add_columns(
            UserCredentials.id.label("_cursor_id"),
            UserCredentials.created_at.label("_cursor_created_at"),
        )

        if next_cursor:
            created_at, record_id = decode_cursor(next_cursor)

            query = (
                query.where(
                    text(
                        "(user_credentials.created_at, user_credentials.id) < (:cur_created_at, :cur_id)"
                    ).bindparams(cur_created_at=created_at, cur_id=record_id)
                )
                .order_by(desc(UserCredentials.created_at), desc(UserCredentials.id))
                .limit(fetch)
            )

            direction = "forward"

        elif prev_cursor:
            created_at, record_id = decode_cursor(prev_cursor)

            query = (
                query.where(
                    text(
                        "(user_credentials.created_at, user_credentials.id) > (:cur_created_at, :cur_id)"
                    ).bindparams(cur_created_at=created_at, cur_id=record_id)
                )
                .order_by(asc(UserCredentials.created_at), asc(UserCredentials.id))
                .limit(fetch)
            )

            direction = "backward"

        else:
            query = query.order_by(
                desc(UserCredentials.created_at), desc(UserCredentials.id)
            ).limit(fetch)

            direction = "forward"

        result = await session.execute(query)
        rows = list(result.mappings().all())

        has_more = len(rows) > limit
        if has_more:
            rows = rows[:limit]

        if direction == "backward":
            rows.reverse()

        if not rows:
            return CursorPage(items=[], next_cursor=None, prev_cursor=None, limit=limit)

        first = rows[0]
        last = rows[-1]

        built_next = (
            encode_cursor(
                last["_cursor_created_at"],
                last["_cursor_id"],
            )
            if has_more or direction == "backward"
            else None
        )
        built_prev = (
            encode_cursor(
                first["_cursor_created_at"],
                first["_cursor_id"],
            )
            if next_cursor or (direction == "backward" and has_more)
            else None
        )

        items = [
            {
                key: value
                for key, value in row.items()
                if key not in {"_cursor_id", "_cursor_created_at"}
            }
            for row in rows
        ]

        return CursorPage(
            items=items,
            next_cursor=built_next,
            prev_cursor=built_prev,
            limit=limit,
        )

    @staticmethod
    async def get_users(
        session: AsyncSession,
        *,
        filters: SearchUserBase | None = None,
        limit: int = 20,
        next_cursor: str | None = None,
        prev_cursor: str | None = None,
        allowed_roles: frozenset[UserRole] | None = None,
    ) -> CursorPage:
        """
        Paginated list of WORK account credentials with identity fields joined.

        role filter allows narrowing to TEACHER or DIRECTOR specifically.
        Without it, all WORK accounts are returned (SYSTEM_ADMIN excluded —
        system admins are not visible to other admins in list views).
        """

        base_join = UserRepositoryBase.get_base_join(_USER_MAPPED_COLUMNS)

        query = base_join.where(UserCredentials.role != UserRole.SYSTEM_ADMIN)

        if allowed_roles is not None:
            query = query.where(UserCredentials.role.in_(allowed_roles))

        query = UserRepositoryBase._apply_filters(query, filters=filters)

        return await UserRepositoryBase._paginate_mapped(
            session,
            query,
            limit=limit,
            next_cursor=next_cursor,
            prev_cursor=prev_cursor,
        )

    @staticmethod
    async def get_user_by_public_id(
        session: AsyncSession,
        public_id: uuid.UUID,
        allowed_roles: frozenset[UserRole] | None = None,
        excluded_roles: frozenset[UserRole] | None = None,
    ) -> RowMapping | None:
        base_join = UserRepositoryBase.get_base_join(_USER_MAPPED_COLUMNS_DETAILED)

        query = base_join.where(UserCredentials.public_id == public_id)

        if allowed_roles is not None:
            query = query.where(UserCredentials.role.in_(allowed_roles))
        if excluded_roles is not None:
            query = query.where(UserCredentials.role.not_in(excluded_roles))

        result = await session.execute(query)

        return result.mappings().one_or_none()


class UserResponseRepository:
    """
    Queries that return flat RowMapping results for direct serialisation
    into response schemas. Kept separate from entity repositories to make
    the distinction between 'load an ORM object for mutation' and
    'fetch a flat read projection for a response' explicit.
    """

    @staticmethod
    async def get_registered_user_response(
        session: AsyncSession, public_id: uuid.UUID
    ) -> RowMapping | None:
        base_join = UserRepositoryBase.get_base_join(_USER_MAPPED_COLUMNS_DETAILED)

        query = base_join.where(UserCredentials.public_id == public_id)

        result = await session.execute(query)

        return result.mappings().one_or_none()
