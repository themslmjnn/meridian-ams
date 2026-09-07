import itertools
import uuid
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from src.core.config import get_settings
from src.core.security import generate_token, hash_password
from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.models.identity import UserIdentity
from src.users.models.login_lockout import UserLoginLockout
from src.users.models.session import UserSession
from src.users.utils.enums import AccountType, UserRole, UserStatus

_counter = itertools.count(1)


def _next() -> int:
    return next(_counter)


async def make_user(
    test_session: AsyncSession,
    *,
    role: UserRole = UserRole.STUDENT,
    account_type: AccountType = AccountType.STUDENT,
    status: UserStatus = UserStatus.ACTIVE,
    firstname: str | None = None,
    lastname: str | None = None,
    middlename: str | None = None,
    phone_number: str | None = None,
    date_of_birth: date | None = None,
    address: str | None = None,
    username: str | None = None,
    email: str | None = None,
    password: str | None = "TestPassword123!",
) -> UserCredentials:
    n = _next()

    new_user_identity = UserIdentity(
        firstname=firstname or "testname",
        lastname=lastname or "testsurname",
        middlename=middlename,
        phone_number=phone_number or f"+992917{n:06d}",
        date_of_birth=date_of_birth
        if date_of_birth is not None
        else (date(2008, 1, 1) if role == UserRole.STUDENT else None),
        address=address,
    )

    test_session.add(new_user_identity)
    await test_session.flush()

    new_user_credentials = UserCredentials(
        identity_id=new_user_identity.id,
        public_id=uuid.uuid4(),
        username=username or f"user_{n}",
        email=email or f"user_{n}@example.com",
        password_hash=await hash_password(password) if password else None,
        role=role,
        account_type=account_type,
        status=status,
    )

    test_session.add(new_user_credentials)
    await test_session.flush()

    _, hashed_activation_token = generate_token()

    if status == UserStatus.PENDING_ACTIVATION:
        new_activation = UserActivation(
            credentials_id=new_user_credentials.id,
            activation_token_hash=hashed_activation_token,
            activation_token_expires_at=(
                datetime.now(UTC)
                + timedelta(hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS)
            ),
        )

        test_session.add(new_activation)

    test_session.add(UserSession(credentials_id=new_user_credentials.id))
    test_session.add(
        UserLoginLockout(
            credentials_id=new_user_credentials.id,
        )
    )

    await test_session.commit()
    await test_session.refresh(new_user_credentials)

    return new_user_credentials


async def make_system_admin(session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        session, role=UserRole.SYSTEM_ADMIN, account_type=AccountType.WORK, **kwargs
    )


async def make_director(session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        session, role=UserRole.DIRECTOR, account_type=AccountType.WORK, **kwargs
    )


async def make_teacher(session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        session, role=UserRole.TEACHER, account_type=AccountType.WORK, **kwargs
    )


async def make_student(session: AsyncSession, **kwargs) -> UserCredentials:
    kwargs.setdefault("date_of_birth", date(2008, 1, 1))

    return await make_user(
        session, role=UserRole.STUDENT, account_type=AccountType.STUDENT, **kwargs
    )


async def make_guardian(session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        session, role=UserRole.GUARDIAN, account_type=AccountType.PERSONAL, **kwargs
    )
