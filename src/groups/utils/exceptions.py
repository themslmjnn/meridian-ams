from sqlalchemy.exc import IntegrityError

from src.core.exceptions import AppException
from src.groups.utils.constants import HTTP404


# HTTP404
class GroupNotFoundError(AppException):
    status_code = 404
    detail = HTTP404.GROUP
    error_code = "GROUP_NOT_FOUND"


# HTTP409
class GroupNameYearConflictError(AppException):
    status_code = 409
    detail = "A group with this name already exists for that academic year"
    error_code = "GROUP_NAME_YEAR_CONFLICT"


class GroupAlreadyArchivedError(AppException):
    status_code = 409
    detail = "Group is already archived"
    error_code = "GROUP_ALREADY_ARCHIVED"


def handle_group_name_per_academic_year(error: IntegrityError) -> None:
    if "uix_group_name_per_academic_year" in str(error.orig):
        raise GroupNameYearConflictError()
