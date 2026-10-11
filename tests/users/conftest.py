import uuid
from unittest.mock import AsyncMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserCredentialsRepository
from src.users.schemas.system_admin import (
    CreateGuardianWithExistingIdentity,
    CreateGuardianWithNewIdentity,
    CreateStaff,
    CreateStudent,
)
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserRole
from src.users.utils.schemas import LoadOptionsSchema
from tests.factories import make_teacher

create_user_request = {
    "firstname": "New",
    "lastname": "User",
    "phone_number": "+992 111 111 101",
    "username": "test_username",
    "email": "new_test_email@gmail.com",
}


@pytest.fixture
def valid_student_payload():
    return CreateStudent(
        **create_user_request,
        type="student",
        date_of_birth="2008-05-01",
    )


@pytest.fixture
def valid_staff_payload():
    create_user_request["email"] = "new_test_email@meridian.edu"

    return CreateStaff(
        **create_user_request,
        role=UserRole.TEACHER,
        type="staff",
    )


@pytest.fixture
def valid_new_guardian_payload():
    return CreateGuardianWithNewIdentity(
        **create_user_request,
        type="new_guardian",
    )


@pytest_asyncio.fixture
async def registered_staff(
    test_session: AsyncSession,
    system_admin: UserCredentials,
    valid_staff_payload: CreateStaff,
) -> UserCredentials:
    response = await UserService.register_user(
        test_session, system_admin.id, valid_staff_payload
    )

    return await UserCredentialsRepository.get_by_public_id(
        test_session,
        response["public_id"],
        load_options=LoadOptionsSchema(load_activation=True, load_login_lockout=True),
    )


@pytest_asyncio.fixture
async def registered_student(
    test_session: AsyncSession,
    system_admin: UserCredentials,
    valid_student_payload: CreateStudent,
) -> UserCredentials:
    response = await UserService.register_user(
        test_session, system_admin.id, valid_student_payload
    )

    return await UserCredentialsRepository.get_by_public_id(
        test_session,
        response["public_id"],
        load_options=LoadOptionsSchema(load_activation=True, load_login_lockout=True),
    )


@pytest_asyncio.fixture
async def registered_new_guardian(
    test_session: AsyncSession,
    system_admin: UserCredentials,
    valid_new_guardian_payload: CreateGuardianWithNewIdentity,
) -> UserCredentials:
    response = await UserService.register_user(
        test_session, system_admin.id, valid_new_guardian_payload
    )

    return await UserCredentialsRepository.get_by_public_id(
        test_session,
        response["public_id"],
        load_options=LoadOptionsSchema(load_activation=True, load_login_lockout=True),
    )


@pytest_asyncio.fixture
async def existing_identity(test_session: AsyncSession) -> UserCredentials:
    return await make_teacher(test_session)


@pytest_asyncio.fixture
async def valid_existing_guardian_payload(
    existing_identity: UserCredentials,
) -> CreateGuardianWithExistingIdentity:
    return CreateGuardianWithExistingIdentity(
        type="existing_guardian",
        existing_identity_id=existing_identity.identity_id,
        username="existing_guardian",
        email="existing.guardian@example.com",
    )


@pytest_asyncio.fixture
async def registered_existing_guardian(
    test_session: AsyncSession,
    system_admin: UserCredentials,
    valid_existing_guardian_payload: CreateGuardianWithExistingIdentity,
) -> UserCredentials:
    response = await UserService.register_user(
        test_session, system_admin.id, valid_existing_guardian_payload
    )

    return await UserCredentialsRepository.get_by_public_id(
        test_session,
        response["public_id"],
        load_options=LoadOptionsSchema(load_activation=True, load_login_lockout=True),
    )


@pytest.fixture
def mock_users_delete_cache_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.delete_cache", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_set_cache_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.set_cache", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_set_cache_director(mocker):
    return mocker.patch("src.users.services.director.set_cache", new_callable=AsyncMock)


@pytest.fixture
def mock_users_delete_cache_shared(mocker):
    return mocker.patch(
        "src.users.services.shared.delete_cache", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_set_cache_shared(mocker):
    return mocker.patch("src.users.services.shared.set_cache", new_callable=AsyncMock)


@pytest.fixture
def mock_users_advisory_lock_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.acquire_contact_locks", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_advisory_lock_shared(mocker):
    return mocker.patch(
        "src.users.services.shared.acquire_contact_locks", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_check_contact_limit_system_admin(mocker):
    return mocker.patch(
        "src.users.services.system_admin.check_contact_limit", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_check_contact_limit_shared(mocker):
    return mocker.patch(
        "src.users.services.shared.check_contact_limit", new_callable=AsyncMock
    )


@pytest.fixture
def idempotency_key() -> str:
    return str(uuid.uuid4())


@pytest.fixture
def mock_register_user_acquire_idempotency_lock(mocker):
    return mocker.patch(
        "src.users.use_cases.register_user.acquire_idempotency_lock",
        new_callable=AsyncMock,
    )


@pytest.fixture
def mock_register_user_complete_idempotency_record(mocker):
    return mocker.patch(
        "src.users.use_cases.register_user.complete_idempotency_record",
        new_callable=AsyncMock,
    )


@pytest.fixture
def mock_register_user_mirror_complete_to_redis_after_commit(mocker):
    return mocker.patch(
        "src.users.use_cases.register_user.mirror_complete_to_redis_after_commit",
        new_callable=AsyncMock,
    )


@pytest.fixture
def mock_users_admin_acquire_contact_locks(mocker):
    return mocker.patch(
        "src.users.services.system_admin.acquire_contact_locks", new_callable=AsyncMock
    )


@pytest.fixture
def mock_users_admin_check_contact_limit(mocker):
    return mocker.patch(
        "src.users.services.system_admin.check_contact_limit", new_callable=AsyncMock
    )

def make_headers(auth: dict) -> dict:
    return {**auth, "Idempotency-Key": str(uuid.uuid4())}
