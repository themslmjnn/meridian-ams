from sqlalchemy.ext.asyncio import AsyncSession

from src.users.schemas.system_admin import SearchUserBase
from src.users.services.system_admin import UserService
from src.users.utils.enums import UserRole, UserStatus
from tests.factories import (
    make_director,
    make_guardian,
    make_student,
    make_system_admin,
    make_teacher,
)

ENDPOINT = "/api/v1/admin/users/guardians"


class TestEmptyResult:
    async def test_returns_empty_page_when_no_guardians_exist(
        self, test_session: AsyncSession
    ):
        page = await UserService.get_guardians(test_session)

        assert page.items == []
        assert page.next_cursor is None
        assert page.prev_cursor is None


class TestRoleFiltering:
    async def test_returns_guardians(self, test_session: AsyncSession):
        await make_guardian(test_session, firstname="GuardianTarget")

        page = await UserService.get_guardians(test_session)

        assert len(page.items) == 1
        assert page.items[0].firstname == "Guardiantarget"
        assert page.items[0].role == UserRole.GUARDIAN

    async def test_excludes_teachers(self, test_session: AsyncSession):
        await make_teacher(test_session)
        await make_guardian(test_session)

        page = await UserService.get_guardians(test_session)

        assert UserRole.TEACHER not in [item.role for item in page.items]

    async def test_excludes_directors(self, test_session: AsyncSession):
        await make_director(test_session)
        await make_guardian(test_session)

        page = await UserService.get_guardians(test_session)

        assert UserRole.DIRECTOR not in [item.role for item in page.items]

    async def test_excludes_students(self, test_session: AsyncSession):
        await make_student(test_session)
        await make_guardian(test_session)

        page = await UserService.get_guardians(test_session)

        assert UserRole.STUDENT not in [item.role for item in page.items]

    async def test_excludes_system_admins(self, test_session: AsyncSession):
        await make_system_admin(test_session)
        await make_guardian(test_session)

        page = await UserService.get_guardians(test_session)

        assert UserRole.SYSTEM_ADMIN not in [item.role for item in page.items]


class TestFilters:
    async def test_filter_by_firstname(self, test_session: AsyncSession):
        await make_guardian(test_session, firstname="Kamola")
        await make_guardian(test_session, firstname="Dilnoza")

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(firstname="Kamo"),
        )

        assert len(page.items) == 1
        assert page.items[0].firstname == "Kamola"

    async def test_filter_by_lastname(self, test_session: AsyncSession):
        await make_guardian(test_session, lastname="Yusupova")
        await make_guardian(test_session, lastname="Toshmatova")

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(lastname="Yusup"),
        )

        assert len(page.items) == 1
        assert page.items[0].lastname == "Yusupova"

    async def test_filter_by_phone_number(self, test_session: AsyncSession):
        await make_guardian(test_session, phone_number="+992901234567")
        await make_guardian(test_session)

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(phone_number="+992901234567"),
        )

        assert len(page.items) == 1
        assert page.items[0].phone_number == "+992901234567"

    async def test_filter_by_email(self, test_session: AsyncSession):
        await make_guardian(test_session, email="findguardian@example.com")
        await make_guardian(test_session)

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(email="findguardian"),
        )

        assert len(page.items) == 1

    async def test_filter_by_status(self, test_session: AsyncSession):
        await make_guardian(test_session, status=UserStatus.ACTIVE)
        await make_guardian(test_session, status=UserStatus.PENDING_ACTIVATION)

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(status=UserStatus.ACTIVE),
        )

        assert len(page.items) == 1

    async def test_no_match_returns_empty(self, test_session: AsyncSession):
        await make_guardian(test_session, firstname="Kamola")

        page = await UserService.get_guardians(
            test_session,
            filters=SearchUserBase(firstname="Zzzzz"),
        )

        assert page.items == []


class TestPagination:
    async def test_limit_caps_results(self, test_session: AsyncSession):
        for _ in range(5):
            await make_guardian(test_session)

        page = await UserService.get_guardians(test_session, limit=3)

        assert len(page.items) == 3
        assert page.next_cursor is not None

    async def test_last_page_has_no_next_cursor(self, test_session: AsyncSession):
        for _ in range(2):
            await make_guardian(test_session)

        page = await UserService.get_guardians(test_session, limit=10)

        assert page.next_cursor is None
