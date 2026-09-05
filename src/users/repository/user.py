from __future__ import annotations

import uuid

from sqlalchemy import RowMapping, Select, asc, desc, func, select, text, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from src.core.pagination import CursorPage, decode_cursor, encode_cursor
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.models.session import UserSession
from src.users.schemas.system_admin import SearchUserBase
from src.users.utils.enums import AccountType, UserRole, UserStatus
from src.users.utils.schemas import LoadOptionsSchema

_CREDENTIALS_IDENTITY_COLUMNS = [
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
]

_BASE_JOIN = select(*_CREDENTIALS_IDENTITY_COLUMNS).join(
    UserIdentity, UserCredentials.identity_id == UserIdentity.id
)


class UserCredentialsRepository:
    @staticmethod
    def _build_load_options(
        query: Select,
        load_options: LoadOptionsSchema | None = None,
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
        *,
        load_options: LoadOptionsSchema | None = None,
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
        account_type: AccountType | None = None,
        allowed_roles: frozenset[UserRole] | None = None,
        excluded_roles: frozenset[UserRole] | None = None,
        load_options: LoadOptionsSchema | None = None,
    ) -> UserCredentials | None:
        query = select(UserCredentials).where(UserCredentials.public_id == public_id)

        if account_type:
            query = query.where(UserCredentials.account_type == account_type)

        if allowed_roles:
            query = query.filter(UserCredentials.role.in_(allowed_roles))
        if excluded_roles:
            query = query.where(UserCredentials.role.not_in(excluded_roles))

        query = UserCredentialsRepository._build_load_options(query, load_options)

        result = await session.execute(query)

        return result.scalar_one_or_none()

    @staticmethod
    async def get_by_username(
        session: AsyncSession,
        username: str,
        load_options: LoadOptionsSchema | None = None,
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
        load_options: LoadOptionsSchema | None = None,
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

    @staticmethod
    async def reactivate_pending_deletion_user(
        session: AsyncSession, public_id: uuid.UUID
    ) -> bool:
        query = (
            update(UserCredentials)
            .where(
                UserCredentials.public_id == public_id,
                UserCredentials.role == UserRole.GUARDIAN,
                UserCredentials.status == UserStatus.PENDING_DELETION,
            )
            .values(
                status=UserStatus.ACTIVE,
                deletion_scheduled_for=None,
            )
        )

        result = await session.execute(query)

        return result.rowcount > 0


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
        query = _BASE_JOIN.where(UserCredentials.public_id == public_id)

        result = await session.execute(query)

        return result.mappings().one_or_none()


class UserRepositoryBase:
    @staticmethod
    def _apply_filters(
        base_query: Select,
        filters: SearchUserBase | None,
        allowed_roles: frozenset[UserRole] | None = None,
    ) -> Select:
        if filters is not None:
            if filters.firstname:
                base_query = base_query.filter(
                    UserCredentials.firstname.ilike(f"%{filters.firstname}%")
                )
            if filters.lastname:
                base_query = base_query.filter(
                    UserCredentials.lastname.ilike(f"%{filters.lastname}%")
                )
            if filters.phone_number:
                base_query = base_query.filter(
                    UserIdentity.phone_number.ilike(f"%{filters.phone_number}%")
                )
            if filters.email:
                base_query = base_query.filter(
                    UserCredentials.email.ilike(f"%{filters.email}%")
                )

        if allowed_roles:
            base_query = base_query.filter(UserCredentials.role.in_(allowed_roles))

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
            encode_cursor(last["created_at"], last["id"])
            if has_more or direction == "backward"
            else None
        )
        built_prev = (
            encode_cursor(first["created_at"], first["id"])
            if next_cursor or (direction == "backward" and has_more)
            else None
        )

        return CursorPage(
            items=rows,
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

        query = (
            _BASE_JOIN.where(
                UserCredentials.account_type == AccountType.WORK,
                UserCredentials.role != UserRole.SYSTEM_ADMIN,
            ),
        )

        query = UserRepositoryBase._apply_filters(
            query,
            filters=filters,
            allowed_roles=allowed_roles,
        )

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
    ) -> RowMapping | None:
        query = _BASE_JOIN.filter(
            UserCredentials.role != UserRole.SYSTEM_ADMIN,
            UserCredentials.role.in_(allowed_roles),
            UserCredentials.public_id == public_id,
        )

        result = await session.execute(query)

        return result.mappings().one_or_none()
