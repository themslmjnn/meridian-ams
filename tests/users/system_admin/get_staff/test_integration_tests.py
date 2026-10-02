import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from src.users.models.credentials import UserCredentials
from src.users.utils.enums import UserRole
from tests.conftest import make_auth_header
from tests.factories import (
    make_guardian,
    make_student,
    make_teacher,
)

ENDPOINT = "/api/v1/admin/users/staff"


class TestAuth:
    async def test_unauthenticated_returns_401(self, integration_client: AsyncClient):
        response = await integration_client.get(ENDPOINT)

        assert response.status_code == 401

    async def test_director_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        director: UserCredentials,
    ):
        headers = await make_auth_header(test_session, director)

        response = await integration_client.get(
            ENDPOINT,
            headers=headers,
        )

        assert response.status_code == 403

    async def test_teacher_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        teacher: UserCredentials,
    ):
        headers = await make_auth_header(test_session, teacher)

        response = await integration_client.get(
            ENDPOINT,
            headers=headers,
        )

        assert response.status_code == 403

    async def test_guardian_returns_403(
        self,
        test_session: AsyncSession,
        integration_client,
        guardian: UserCredentials,
    ):
        headers = await make_auth_header(test_session, guardian)

        response = await integration_client.get(
            ENDPOINT,
            headers=headers,
        )

        assert response.status_code == 403


class TestSuccess:
    async def test_returns_200(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(ENDPOINT, headers=headers)

        assert response.status_code == 200

    async def test_response_shape(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        await make_teacher(test_session)
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(ENDPOINT, headers=headers)
        data = response.json()

        assert "items" in data
        assert "next_cursor" in data
        assert "prev_cursor" in data
        assert "limit" in data

        if data["items"]:
            item = data["items"][0]
            assert "phone_number" in item
            assert "role" in item
            assert "firstname" in item
            assert "lastname" in item

    async def test_staff_roles_only_in_response(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        await make_student(test_session)
        await make_guardian(test_session)
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(ENDPOINT, headers=headers)
        data = response.json()

        roles = {item["role"] for item in data["items"]}
        assert roles.issubset({UserRole.TEACHER.value, UserRole.DIRECTOR.value})


class TestCursorValidation:
    async def test_tampered_cursor_returns_422(
        self,
        test_session: AsyncSession,
        integration_client: AsyncClient,
        system_admin: UserCredentials,
    ):
        headers = await make_auth_header(test_session, system_admin)

        response = await integration_client.get(
            ENDPOINT,
            params={"next_cursor": "definitely-not-a-valid-cursor"},
            headers=headers,
        )

        assert response.status_code == 422
