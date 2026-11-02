import re
from datetime import date

import phonenumbers
from pydantic_core import PydanticCustomError

from meridian_ams.users.utils.constants import STUDENT_MAX_AGE, STUDENT_MIN_AGE

_NAME_PATTERN = re.compile(r"^[A-Za-zÀ-ÖØ-öø-ÿ]+(?:['\-][A-Za-zÀ-ÖØ-öø-ÿ]+)*$")


def validate_name(value: str, field: str) -> str:
    if not _NAME_PATTERN.fullmatch(value):
        raise PydanticCustomError(
            f"invalid_{field}_characters",
            f"{field.capitalize()} can only contain letters, hyphens, and apostrophes",
        )

    return re.sub(
        r"([A-Za-zÀ-ÖØ-öø-ÿ]+)",
        lambda m: m.group(0).capitalize(),
        value,
    )


def validate_date_of_birth(birth_date: date) -> date:
    today = date.today()

    if birth_date >= today:
        raise PydanticCustomError(
            "date_of_birth_not_in_past",
            "Date of birth must be in the past",
        )

    age = (
        today.year
        - birth_date.year
        - ((today.month, today.day) < (birth_date.month, birth_date.day))
    )

    if age < STUDENT_MIN_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_young",
            f"User must be at least {STUDENT_MIN_AGE} years old",
        )
    if age > STUDENT_MAX_AGE:
        raise PydanticCustomError(
            "date_of_birth_too_old",
            f"Student must be {STUDENT_MAX_AGE} years old or younger",
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


_EMAIL_PATTERN = re.compile(
    r"^[A-Za-z0-9][A-Za-z0-9.+_-]*@[A-Za-z0-9][A-Za-z0-9.-]*\.[A-Za-z]{2,}$"
)


def validate_email(email: str) -> str:
    if not _EMAIL_PATTERN.fullmatch(email.strip()):
        raise PydanticCustomError(
            "invalid_email",
            "Invalid email address",
        )

    return email.strip().lower()


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
