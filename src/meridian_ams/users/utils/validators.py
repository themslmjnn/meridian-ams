import re
import unicodedata
from datetime import date
from typing import Annotated

import phonenumbers
from email_validator import EmailNotValidError
from email_validator import validate_email as _validate_email_address
from pydantic import BeforeValidator, Field
from pydantic_core import PydanticCustomError

from meridian_ams.users.utils.constants import (
    NON_STUDENT_MAX_AGE,
    NON_STUDENT_MIN_AGE,
    STUDENT_MAX_AGE,
    STUDENT_MIN_AGE,
)
from meridian_ams.users.utils.helpers import calculate_age

_LATIN = "A-Za-zÀ-ÖØ-öø-ÿ"
_CYRILLIC = "А-Яа-яЁё"
_NAME_PATTERNS = tuple(
    re.compile(rf"[{alpha}]+(?:[ '\-][{alpha}]+)*") for alpha in (_LATIN, _CYRILLIC)
)


def _nfc(value: object) -> object:
    return unicodedata.normalize("NFC", value) if isinstance(value, str) else value


NameStr = Annotated[str, BeforeValidator(_nfc), Field(min_length=3, max_length=30)]


def validate_name(value: str, field: str) -> str:
    if not any(p.fullmatch(value) for p in _NAME_PATTERNS):
        raise PydanticCustomError(
            f"invalid_{field}_characters",
            f"{field.replace('_', ' ').capitalize()} must use only Latin or only "
            "Russian letters, with optional hyphens or apostrophes",
        )
    return value


def validate_date_of_birth_student(birth_date: date) -> date:
    today = date.today()

    if birth_date >= today:
        raise PydanticCustomError(
            "date_of_birth_not_in_past",
            "Date of birth must be in the past",
        )

    age = calculate_age(birth_date, today)

    if age < STUDENT_MIN_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_young",
            f"Student must be at least {STUDENT_MIN_AGE} years old",
        )

    if age > STUDENT_MAX_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_old",
            f"Student must be {STUDENT_MAX_AGE} years old or younger",
        )

    return birth_date


def validate_date_of_birth_non_student(birth_date: date) -> date:
    today = date.today()

    if birth_date >= today:
        raise PydanticCustomError(
            "date_of_birth_not_in_past",
            "Date of birth must be in the past",
        )

    age = calculate_age(birth_date, today)

    if age < NON_STUDENT_MIN_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_young",
            f"User must be at least {NON_STUDENT_MIN_AGE} years old",
        )

    if age > NON_STUDENT_MAX_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_old",
            f"User must be {NON_STUDENT_MAX_AGE} years old or younger",
        )

    return birth_date


def validate_phone_number(phone_number: str) -> str:
    phone_number = phone_number.strip()

    try:
        parsed = phonenumbers.parse(phone_number, None)

    except phonenumbers.NumberParseException as exc:
        raise PydanticCustomError(
            "phone_number_invalid_format",
            "Phone number must be in international format, e.g. +14155552671",
        ) from exc

    if not phonenumbers.is_valid_number(parsed):
        raise PydanticCustomError(
            "phone_number_invalid",
            "Phone number is not a valid number for its country",
        )

    number_type = phonenumbers.number_type(parsed)
    if number_type not in (
        phonenumbers.PhoneNumberType.MOBILE,
        phonenumbers.PhoneNumberType.FIXED_LINE_OR_MOBILE,
    ):
        raise PydanticCustomError(
            "phone_number_not_mobile",
            "Phone number must be a mobile number",
        )

    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)


def validate_username(username: str) -> str:
    if not re.fullmatch(r"[a-z0-9._]+", username):
        raise PydanticCustomError(
            "invalid_username_characters",
            "Username can only contain lowercase letters, numbers, (.) and (_)",
        )

    if not username[0].isalpha():
        raise PydanticCustomError(
            "invalid_username_start",
            "Username must start with a letter",
        )

    if username[-1] in (".", "_"):
        raise PydanticCustomError(
            "invalid_username_end",
            "Username cannot end with (.) or (_)",
        )

    if re.search(r"[._]{2}", username):
        raise PydanticCustomError(
            "invalid_username_consecutive",
            "Username cannot contain consecutive (.) or (_) characters",
        )

    return username


def validate_email(email: str) -> str:
    try:
        result = _validate_email_address(
            email.strip(), check_deliverability=False, allow_smtputf8=False
        )

    except EmailNotValidError as exc:
        raise PydanticCustomError("invalid_email", "Invalid email address") from exc

    local = result.normalized.rpartition("@")[0]
    if "+" in local:
        raise PydanticCustomError(
            "email_plus_alias_not_allowed", "Email must not contain a '+' alias"
        )

    return result.normalized.lower()


def validate_work_email_domain_staff(email: str) -> None:
    from meridian_ams.core.config import get_settings

    settings = get_settings()

    domain = email.split("@")[-1]
    if domain != settings.WORK_EMAIL_DOMAIN:
        raise PydanticCustomError(
            "invalid_work_email_domain",
            f"Staff email must use the school domain @{settings.WORK_EMAIL_DOMAIN}",
        )


def validate_work_email_domain_non_staff(email: str) -> None:
    from meridian_ams.core.config import get_settings

    settings = get_settings()

    domain = email.split("@")[-1]
    if domain == settings.WORK_EMAIL_DOMAIN:
        raise PydanticCustomError(
            "work_email_domain_used",
            f"Non staff email must not use the school domain @{settings.WORK_EMAIL_DOMAIN}",
        )
