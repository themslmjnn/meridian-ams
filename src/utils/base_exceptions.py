from sqlalchemy.exc import IntegrityError


def raise_unhandled_integrity_error(error: IntegrityError) -> None:
    raise error
