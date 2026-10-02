import uuid
from datetime import UTC, datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from src.emails.repository import EmailRepository
from src.users.models.activation import UserActivation
from src.users.models.credentials import UserCredentials
from src.users.repository.user import UserActivationRepository
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserStatus
from src.users.utils.exceptions import (
    ActivationRowMissingError,
    CredentialsNotFoundError,
    UserNotPendingActivationError,
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
            await UserService.resend_activation_token(
                test_session, system_admin.id, uuid.uuid4()
            )

    async def test_system_admin_public_id_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        with pytest.raises(CredentialsNotFoundError):
            await UserService.resend_activation_token(
                test_session, system_admin.id, system_admin.public_id
            )


class TestStatusValidation:
    @pytest.mark.parametrize(
        "status",
        [
            UserStatus.ACTIVE,
            UserStatus.DEACTIVATED,
            UserStatus.PENDING_DELETION,
        ],
    )
    async def test_non_pending_status_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
        status: UserStatus,
    ):
        user = await make_teacher(test_session, status=status)

        with pytest.raises(UserNotPendingActivationError):
            await UserService.resend_activation_token(
                test_session, system_admin.id, user.public_id
            )


class TestMissingActivationRow:
    async def test_missing_activation_row_raises(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        await test_session.execute(
            UserActivation.__table__.delete().where(
                UserActivation.credentials_id == pending.id
            )
        )
        await test_session.flush()

        with pytest.raises(ActivationRowMissingError):
            await UserService.resend_activation_token(
                test_session, system_admin.id, pending.public_id
            )


class TestSuccess:
    async def test_activation_token_replaced(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        old_result = await UserActivationRepository.get_by_credentials_id(
            test_session, pending.id
        )
        old_hash = old_result.activation_token_hash

        await UserService.resend_activation_token(
            test_session, system_admin.id, pending.public_id
        )

        await test_session.refresh(old_result)

        assert old_result.activation_token_hash != old_hash

    async def test_activation_expiry_extended(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        await UserService.resend_activation_token(
            test_session, system_admin.id, pending.public_id
        )

        result = await UserActivationRepository.get_by_credentials_id(
            test_session, pending.id
        )

        assert result.activation_token_expires_at > datetime.now(UTC)

    async def test_activation_email_queued(
        self,
        test_session: AsyncSession,
        system_admin: UserCredentials,
    ):
        pending = await make_teacher(test_session, status=UserStatus.PENDING_ACTIVATION)

        await UserService.resend_activation_token(
            test_session, system_admin.id, pending.public_id
        )

        result = await EmailRepository.get_by_triggered_by(
            test_session, system_admin.id
        )

        assert result is not None
        assert result[0].triggered_by == system_admin.id
