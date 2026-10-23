from pydantic_core import PydanticCustomError


def validate_academic_year(value: str) -> str:
    first, second = value.split("-")

    if int(second) != int(first) + 1:
        raise PydanticCustomError(
            "incorrect_academic_year",
            "Second year must be exactly one year after the first",
        )

    return value
