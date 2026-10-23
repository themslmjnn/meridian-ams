from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException


class GroupNameYearConflictError(AppException):
    status_code = 409
    detail = "A group with this name already exists for that academic year"
    error_code = "GROUP_NAME_YEAR_CONFLICT"


def handle_group_name_per_academic_year(error: IntegrityError) -> None:
    if "uix_group_name_per_academic_year" in str(error.orig):
        raise GroupNameYearConflictError()
