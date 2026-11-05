from sqlalchemy.exc import DBAPIError

LOCK_NOT_AVAILABLE_SQLSTATE = "55P03"


def is_lock_timeout(exc: DBAPIError) -> bool:
    orig = exc.orig
    sqlstate = getattr(orig, "sqlstate", None) or getattr(
        getattr(orig, "__cause__", None), "sqlstate", None
    )
    return sqlstate == LOCK_NOT_AVAILABLE_SQLSTATE
