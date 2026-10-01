import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.emails.repository import EmailRepository
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserPasswordResetRepository
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    CredentialsNotFoundError,
    InvalidStatusTransitionError,
)
from tests.factories import make_teacher

ENDPOINT = "/api/v1/admin/users"


class TestNotFound:
    async def test_unknown_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        with pytest.raises(CredentialsNotFoundError):
            await UserService.create_reset_password_request(
                test_session, system_admin.id, uuid.uuid4()
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        with pytest.raises(CredentialsNotFoundError):
            await UserService.create_reset_password_request(
                test_session, system_admin.id, system_admin.public_id
            )


class TestStatusValidation:
    @pytest.mark.parametrize(
        "status",
        [
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_ACTIVATION,
            UserStatus.PENDING_DELETION,
        ],
    )
    async def test_non_active_status_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        status: UserStatus,
    ):
        user = await make_teacher(test_session, status=status)

        with pytest.raises(InvalidStatusTransitionError):
            await UserService.create_reset_password_request(
                test_session, system_admin.id, user.public_id
            )


class TestPasswordResetRow:
    async def test_creates_new_row_when_none_exists(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ):
        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        password_reset_row = await UserPasswordResetRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert password_reset_row is not None
        assert password_reset_row.reset_password_token_hash is not None
        assert password_reset_row.reset_password_token_expires_at > datetime.now(UTC)

    async def test_updates_existing_row_in_place(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ) -> None:
        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        password_reset_row = await UserPasswordResetRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        first_hash = password_reset_row.reset_password_token_hash

        await test_session.refresh(teacher, ["password_reset"])

        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        result = await UserPasswordResetRepository.get_by_credentials_id(
            test_session, teacher.id
        )

        assert result.reset_password_token_hash != first_hash
        assert result.reset_password_token_expires_at > datetime.now(UTC)

    async def test_token_hash_differs_between_requests(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ):
        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        password_reset_row = await UserPasswordResetRepository.get_by_credentials_id(
            test_session, teacher.id
        )
        first_hash = password_reset_row.reset_password_token_hash

        second_teacher = await make_teacher(test_session)
        await UserService.create_reset_password_request(
            test_session, system_admin.id, second_teacher.public_id
        )

        password_reset_row = await UserPasswordResetRepository.get_by_credentials_id(
            test_session, second_teacher.id
        )
        second_hash = password_reset_row.reset_password_token_hash

        assert first_hash != second_hash


class TestPasswordResetEmail:
    async def test_reset_email_queued(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ):
        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        result = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert result is not None
        assert result[0].triggered_by == system_admin.id

    async def test_second_request_queues_second_email(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        teacher: UserCredentials,
    ):
        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        await test_session.refresh(teacher, ["password_reset"])

        await UserService.create_reset_password_request(
            test_session, system_admin.id, teacher.public_id
        )

        result = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert len(result) == 2
