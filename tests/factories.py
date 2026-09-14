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
    failed_attempts: int | None = None,
    locked_until: datetime | None = None,
) -> UserCredentials:
    n = _next()

    identity = UserIdentity(
        firstname=firstname.capitalize() if firstname is not None else "Testname",
        lastname=lastname.capitalize() if lastname is not None else "Testsurname",
        middlename=middlename.capitalize() if middlename is not None else middlename,
        phone_number=phone_number or f"+992917{n:06d}",
        date_of_birth=date_of_birth
        if date_of_birth is not None
        else (date(2008, 1, 1) if role == UserRole.STUDENT else None),
        address=address,
    )

    test_session.add(identity)
    await test_session.flush()

    credentials = UserCredentials(
        identity_id=identity.id,
        public_id=uuid.uuid4(),
        username=username or f"user_{n}",
        email=email or f"user_{n}@example.com",
        password_hash=await hash_password(password) if password else None,
        role=role,
        account_type=account_type,
        status=status,
    )

    test_session.add(credentials)
    await test_session.flush()

    _, hashed_activation_token = generate_token()

    if status == UserStatus.PENDING_ACTIVATION:
        new_activation = UserActivation(
            credentials_id=credentials.id,
            activation_token_hash=hashed_activation_token,
            activation_token_expires_at=(
                datetime.now(UTC)
                + timedelta(hours=get_settings().ACTIVATION_TOKEN_EXPIRES_HOURS)
            ),
        )

        test_session.add(new_activation)

    test_session.add(UserSession(credentials_id=credentials.id))
    test_session.add(
        UserLoginLockout(
            credentials_id=credentials.id,
            failed_attempts=failed_attempts,
            locked_until=locked_until,
        )
    )

    await test_session.commit()
    await test_session.refresh(credentials)

    return credentials


async def make_system_admin(test_session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        test_session,
        role=UserRole.SYSTEM_ADMIN,
        account_type=AccountType.WORK,
        **kwargs,
    )


async def make_director(test_session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        test_session, role=UserRole.DIRECTOR, account_type=AccountType.WORK, **kwargs
    )


async def make_teacher(test_session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        test_session, role=UserRole.TEACHER, account_type=AccountType.WORK, **kwargs
    )


async def make_student(test_session: AsyncSession, **kwargs) -> UserCredentials:
    kwargs.setdefault("date_of_birth", date(2008, 1, 1))

    return await make_user(
        test_session, role=UserRole.STUDENT, account_type=AccountType.STUDENT, **kwargs
    )


async def make_guardian(test_session: AsyncSession, **kwargs) -> UserCredentials:
    return await make_user(
        test_session,
        role=UserRole.GUARDIAN,
        account_type=AccountType.PERSONAL,
        **kwargs,
    )
