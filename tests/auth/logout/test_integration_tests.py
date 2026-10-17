from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.auth.tokens import create_access_token
from src.users.models.credentials import UserCredentials
from src.users.models.session import UserSession
from src.users.repository.session import UserSessionRepository
from tests.auth.conftest import get_sessions, seed_sessions
from tests.conftest import make_auth_header
from tests.endpoints import AuthEndpoints, UserEndpoints


def _header_for(credentials: UserCredentials, user_session: UserSession):
    token = create_access_token(
        public_id=credentials.public_id,
        role=credentials.role,
        account_type=credentials.account_type,
        session_id=user_session.id,
        access_token_version=user_session.access_token_version,
    )

    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.post(AuthEndpoints.LOGOUT)

        assert response.status_code == 401

    async def test_malformed_token_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.post(
            AuthEndpoints.LOGOUT, headers={"Authorization": "Bearer not-a-jwt"}
        )

        assert response.status_code == 401


class TestSuccessfulLogout:
    async def test_returns_204_with_empty_body(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)

        assert response.status_code == 204
        assert response.content == b""

    async def test_removes_session_row(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)
        session_id = (await get_sessions(test_session, teacher.id))[0].id

        await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)

        assert await UserSessionRepository.get_by_id(test_session, session_id) is None

    async def test_clears_refresh_cookies(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)

        cookies = {
            header.split("=", 1)[0]: header.lower()
            for header in response.headers.get_list("set-cookie")
        }

        assert set(cookies) == {"refresh_token", "refresh_token_family"}
        for header in cookies.values():
            assert "max-age=0" in header
            assert f"path={AuthEndpoints.REFRESH}" in header


class TestTokenAfterLogout:
    async def test_access_token_rejected_after_logout(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        before = await integration_client.get(UserEndpoints.ME, headers=headers)
        await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)
        after = await integration_client.get(UserEndpoints.ME, headers=headers)

        assert before.status_code == 200
        assert after.status_code == 401

    async def test_second_logout_with_same_token_returns_401(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        first = await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)
        second = await integration_client.post(AuthEndpoints.LOGOUT, headers=headers)

        assert first.status_code == 204
        assert second.status_code == 401

    async def test_other_session_token_still_valid(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        teacher: UserCredentials,
    ):
        current_headers = await make_auth_header(test_session, teacher)
        other = (await seed_sessions(test_session, teacher.id, 1))[0]
        other_headers = _header_for(teacher, other)

        await integration_client.post(AuthEndpoints.LOGOUT, headers=current_headers)

        response = await integration_client.get(UserEndpoints.ME, headers=other_headers)

        assert response.status_code == 200
