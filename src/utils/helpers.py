from pydantic import BaseModel

from src.database.connection import MutableBase
from src.utils.exceptions import NoChangesDetectedError


def update_object(instance: MutableBase, request: BaseModel) -> None:
    changed = False

    for field, value in request.model_dump(
        exclude_unset=True, exclude={"type"}
    ).items():
        if getattr(instance, field) != value:
            setattr(instance, field, value)
            changed = True

    if not changed:
        raise NoChangesDetectedError()
