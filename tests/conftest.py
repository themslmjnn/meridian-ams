from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
import redis.asyncio as aioredis
from fastapi import Request
from httpx import ASGITransport, AsyncClient
from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from src.auth.repository import AuthRepository
from src.auth.schemas import CreateAccessToken
from src.core.caching import get_redis, get_settings
from src.core.dependencies import get_session
from src.core.security import create_access_token
from src.database.connection import ImmutableBase
from src.main import app
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository
from src.users.schemas.system_admin import (
    CreateGuardianAdminWithExistingIdentity,
    CreateGuardianAdminWithNewIdentity,
    CreateStaffAdmin,
    CreateStudentAdmin,
)
from src.users.utils.enums import UserRole
from src.users.utils.schemas import LoadOptionsSchema
from tests.factories import (
    make_director,
    make_guardian,
    make_student,
    make_system_admin,
    make_teacher,
)

settings = get_settings()

SYNC_DB_URL = (
    f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PSSW}"
    f"@{settings.DB_HOST}:{settings.DB_PORT}/{settings.DB_NAME}"
)

test_engine = create_async_engine(url=settings.DATABASE_URL, poolclass=NullPool)


@pytest.fixture(scope="session", autouse=True)
def _guard_test_environment():
    if settings.ENVIRONMENT != "test":
        pytest.exit(
            f"Refusing to run tests: ENVIRONMENT is '{settings.ENVIRONMENT}', "
            "expected 'test'. This guard exists because the test suite "
            "creates and drops the full schema — running it against a "
            "non-test database would destroy real data."
        )


@pytest.fixture(scope="session", autouse=True)
def clear_settings_cache(_guard_test_environment) -> None:  # type: ignore[misc]
    """Clear the lru_cache on get_settings before and after the test session."""
    get_settings.cache_clear()

    yield  # type: ignore[misc]

    get_settings.cache_clear()


@pytest.fixture(scope="session", autouse=True)
def create_tables(_guard_test_environment):
    sync_engine = create_engine(SYNC_DB_URL)

    with sync_engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        conn.commit()

    ImmutableBase.metadata.create_all(sync_engine)

    yield

    ImmutableBase.metadata.drop_all(sync_engine)
    sync_engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def test_session():
    async with test_engine.connect() as conn:
        await conn.begin()

        session = AsyncSession(bind=conn, expire_on_commit=False)

        async def override_get_session():
            yield session

        app.dependency_overrides[get_session] = override_get_session

        try:
            yield session

        finally:
            try:
                await session.close()
                await conn.rollback()

            except Exception as e:
                print(f"Teardown error: {e}")

            finally:
                app.dependency_overrides.clear()


@pytest_asyncio.fixture(scope="function")
async def integration_client(test_session):
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as async_client:
        yield async_client


@pytest_asyncio.fixture(scope="function")
async def redis_client():
    client = aioredis.from_url(
        settings.REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
    )

    await client.flushdb()

    yield client

    await client.flushdb()
    await client.aclose()


@pytest_asyncio.fixture(scope="function", autouse=True)
async def override_redis(redis_client):
    async def get_test_redis():
        return redis_client

    app.dependency_overrides[get_redis] = get_test_redis

    yield

    app.dependency_overrides.pop(get_redis, None)


@pytest.fixture
def database_health_mock(mocker):
    return mocker.patch(
        "src.api.health._check_database",
        new_callable=AsyncMock,
        return_value={"status": "ok", "duration_ms": 1.0},
    )


@pytest.fixture
def redis_health_mock(mocker):
    return mocker.patch(
        "src.api.health._check_redis",
        new_callable=AsyncMock,
        return_value={"status": "ok", "duration_ms": 1.0},
    )


async def make_auth_header(
    request: Request, session: AsyncSession, user: UserCredentials
) -> dict:
    user_credentials = await UserCredentialsRepository.get_by_public_id(
        session, user.public_id, load_options=LoadOptionsSchema(load_sessions=True)
    )

    incoming_device_id = request.cookies.get("device_id")
    if incoming_device_id:
        existing_session = await AuthRepository.get_session_by_device_id(
            session,
            credentials_id=user_credentials.id,
            device_id=incoming_device_id,
        )

    token = create_access_token(
        CreateAccessToken(
            sub=user_credentials.public_id,
            role=user_credentials.role,
            account_type=user_credentials.account_type,
            session_id=existing_session.id,
            atv=existing_session.access_token_version,
        )
    )

    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture
async def system_admin(test_session):
    return await make_system_admin(test_session)


@pytest_asyncio.fixture
async def director(test_session):
    return await make_director(test_session)


@pytest_asyncio.fixture
async def teacher(test_session):
    return await make_teacher(test_session)


@pytest_asyncio.fixture
async def student(test_session):
    return await make_student(test_session)


@pytest_asyncio.fixture
async def guardian(test_session):
    return await make_guardian(test_session)


create_user_request = {
    "firstname": "New",
    "lastname": "User",
    "phone_number": "+992 111 111 101",
    "username": "new_test_username",
    "email": "new_test_email@gmail.com",
}


@pytest.fixture
def valid_student_payload():
    return CreateStudentAdmin(
        **create_user_request,
        type="student",
        date_of_birth="2008-05-01",
    )


@pytest.fixture
def valid_staff_payload():
    return CreateStaffAdmin(
        **create_user_request,
        role=UserRole.TEACHER,
        type="staff",
    )


@pytest.fixture
def valid_new_guardian_payload():
    return CreateGuardianAdminWithNewIdentity(
        **create_user_request,
        type="new_guardian",
    )


@pytest.fixture
def valid_existing_guardian_payload():
    return CreateGuardianAdminWithExistingIdentity(
        type="existing_guardian",
        existing_identity_id=999999,
        username="new_test_username",
        email="new_test_email@gmail.com",
    )


@pytest.fixture
def mock_users_delete_cache_system_admin(mocker):
    return mocker.patch("src.users.services.system_admin.delete_cache")


@pytest.fixture
def mock_users_set_cache_system_admin(mocker):
    return mocker.patch("src.users.services.system_admin.set_cache")


@pytest.fixture
def mock_users_set_cache_director(mocker):
    return mocker.patch("src.users.services.director.set_cache")

@pytest.fixture
def mock_users_delete_cache_shared(mocker):
    return mocker.patch("src.users.services.shared.delete_cache")


@pytest.fixture
def mock_users_set_cache_shared(mocker):
    return mocker.patch("src.users.services.shared.set_cache")



@pytest.fixture
def mock_users_advisory_lock_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.acquire_contact_locks"
    )


@pytest.fixture
def mock_users_advisory_lock_shared(mocker):
    return mocker.patch(
        "src.users.services.shared.acquire_contact_locks"
    )


@pytest.fixture
def mock_users_check_contact_limit_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.check_contact_limit"
    )


@pytest.fixture
def mock_users_check_contact_limit_shared(mocker):
    return mocker.patch(
        "src.users.services.shared.check_contact_limit"
    )


@pytest.fixture
def mock_send_account_info_updated_email(mocker):
    return mocker.patch(
        "src.users.services.system_admin.emails.send_account_info_updated_email"
    )


@pytest.fixture
def mock_send_account_deactivation_email(mocker):
    return mocker.patch(
        "src.users.services.system_admin.emails.send_account_deactivation_email"
    )


@pytest.fixture
def mock_send_account_activation_email(mocker):
    return mocker.patch(
        "src.users.services.system_admin.emails.send_account_activation_email"
    )

@pytest.fixture
def mock_send_account_deletion_email(mocker):
    return mocker.patch(
        "src.users.services.system_admin.emails.send_account_deletion_email"
    )


@pytest.fixture
def mock_send_account_deletion_canceled_email(mocker):
    return mocker.patch(
        "src.users.services.system_admin.emails.send_account_deletion_canceled_email"
    )


@pytest.fixture
def mock_send_email_change_verification(mocker):
    return mocker.patch(
        "src.users.services.shared.emails.send_email_change_verification"
    )


@pytest.fixture
def mock_send_email_changed_notification(mocker):
    return mocker.patch(
        "src.users.services.shared.emails.send_email_changed_notification"
    )


@pytest.fixture
def mock_send_password_changed_notification(mocker):
    return mocker.patch(
        "src.users.services.shared.emails.send_password_changed_notification"

    )

@pytest.fixture
def mock_send_account_self_deletion_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_deletion_email"
    )


@pytest.fixture
def mock_send_account_info_self_updated_email(mocker):
    return mocker.patch(
        "src.users.services.guardian.emails.send_account_info_updated_email"
    )
