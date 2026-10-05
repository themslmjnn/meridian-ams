from sqlalchemy.ext.asyncio import AsyncSession

from src.users.schemas.system_admin import SearchUserBase
from src.users.services.director import UserServiceDirector
from src.users.utils.enums import UserRole, UserStatus
from tests.factories import (
    make_director,
    make_guardian,
    make_student,
    make_system_admin,
    make_teacher,
)

ENDPOINT = "/api/v1/director/users/staff"


class TestEmptyResult:
    async def test_returns_empty_page_when_no_staff_exist(
        self, test_session: AsyncSession
    ):
        page = await UserServiceDirector.get_staff(test_session)

        assert page.items == []
        assert page.next_cursor is None
        assert page.prev_cursor is None


class TestRoleFiltering:
    async def test_returns_teachers(self, test_session: AsyncSession):
        await make_teacher(test_session, firstname="TeacherTarget")

        page = await UserServiceDirector.get_staff(test_session)

        assert page.items[0].firstname == "Teachertarget"
        assert page.items[0].role == UserRole.TEACHER

    async def test_doesnot_return_directors(self, test_session: AsyncSession):
        await make_director(test_session, firstname="DirectorTarget")
        await make_student(test_session)

        page = await UserServiceDirector.get_staff(test_session)

        assert "Directortarget" not in [item.firstname for item in page.items]
        assert UserRole.DIRECTOR not in [item.role for item in page.items]

    async def test_excludes_students(self, test_session: AsyncSession):
        await make_student(test_session)
        await make_teacher(test_session)

        page = await UserServiceDirector.get_staff(test_session)

        assert UserRole.STUDENT not in [item.role for item in page.items]

    async def test_excludes_guardians(self, test_session: AsyncSession):
        await make_guardian(test_session)
        await make_teacher(test_session)

        page = await UserServiceDirector.get_staff(test_session)

        assert UserRole.GUARDIAN not in [item.role for item in page.items]

    async def test_excludes_system_admins(self, test_session: AsyncSession):
        await make_system_admin(test_session, firstname="AdminTarget")
        await make_teacher(test_session)

        page = await UserServiceDirector.get_staff(test_session)

        assert UserRole.SYSTEM_ADMIN not in [item.role for item in page.items]


class TestFilters:
    async def test_filter_by_firstname(self, test_session: AsyncSession):
        await make_teacher(test_session, firstname="Rustam")
        await make_teacher(test_session, firstname="Dilnoza")

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(firstname="Rust"),
        )

        assert len(page.items) == 1
        assert page.items[0].firstname == "Rustam"

    async def test_filter_by_lastname(self, test_session: AsyncSession):
        await make_teacher(test_session, lastname="Karimov")
        await make_teacher(test_session, lastname="Toshmatov")

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(lastname="Karim"),
        )

        assert len(page.items) == 1
        assert page.items[0].lastname == "Karimov"

    async def test_filter_by_phone_number(self, test_session: AsyncSession):
        await make_teacher(
            test_session,
            firstname="PhoneTarget",
            phone_number="+992901234567",
        )
        await make_teacher(test_session, firstname="OtherTeacher")

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(phone_number="+992901234567"),
        )

        assert len(page.items) == 1
        assert page.items[0].firstname == "Phonetarget"
        assert page.items[0].phone_number == "+992901234567"

    async def test_filter_by_email(self, test_session: AsyncSession):
        await make_teacher(
            test_session,
            firstname="EmailTarget",
            email="findme@meridian.edu",
        )
        await make_teacher(test_session, firstname="OtherTeacher")

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(email="findme"),
        )

        assert len(page.items) == 1
        assert page.items[0].firstname == "Emailtarget"

    async def test_filter_by_status(self, test_session: AsyncSession):
        await make_teacher(
            test_session,
            firstname="ActiveTeacher",
            status=UserStatus.ACTIVE,
        )
        await make_teacher(
            test_session,
            firstname="PendingTeacher",
            status=UserStatus.PENDING_ACTIVATION,
        )

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(status=UserStatus.ACTIVE),
        )

        assert len(page.items) == 1
        assert page.items[0].firstname == "Activeteacher"

    async def test_no_match_returns_empty(self, test_session: AsyncSession):
        await make_teacher(test_session, firstname="Bobur")

        page = await UserServiceDirector.get_staff(
            test_session,
            filters=SearchUserBase(firstname="Zzzzz"),
        )

        assert page.items == []


class TestPagination:
    async def test_limit_caps_results(self, test_session: AsyncSession):
        for i in range(5):
            await make_teacher(
                test_session,
                firstname=f"Teacher{i}",
            )

        page = await UserServiceDirector.get_staff(test_session, limit=3)

        assert len(page.items) == 3
        assert page.next_cursor is not None

    async def test_next_cursor_advances_page(self, test_session: AsyncSession):
        for i in range(4):
            await make_teacher(
                test_session,
                firstname=f"Teacher{i}",
            )

        first_page = await UserServiceDirector.get_staff(test_session, limit=2)

        assert first_page.next_cursor is not None

        second_page = await UserServiceDirector.get_staff(
            test_session,
            limit=2,
            next_cursor=first_page.next_cursor,
        )

        first_names = {item.firstname for item in first_page.items}
        second_names = {item.firstname for item in second_page.items}

        assert first_names.isdisjoint(second_names)

    async def test_prev_cursor_returns_previous_page(self, test_session: AsyncSession):
        for i in range(4):
            await make_teacher(
                test_session,
                firstname=f"Teacher{i}",
            )

        first_page = await UserServiceDirector.get_staff(test_session, limit=2)

        second_page = await UserServiceDirector.get_staff(
            test_session,
            limit=2,
            next_cursor=first_page.next_cursor,
        )

        assert second_page.prev_cursor is not None

        recovered = await UserServiceDirector.get_staff(
            test_session,
            limit=2,
            prev_cursor=second_page.prev_cursor,
        )

        first_names = {item.firstname for item in first_page.items}
        recovered_names = {item.firstname for item in recovered.items}

        assert first_names == recovered_names

    async def test_last_page_has_no_next_cursor(self, test_session: AsyncSession):
        for i in range(2):
            await make_teacher(
                test_session,
                firstname=f"Teacher{i}",
            )

        page = await UserServiceDirector.get_staff(test_session, limit=10)

        assert page.next_cursor is None
