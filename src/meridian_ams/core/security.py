import hashlib
import hmac
import secrets


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def generate_token() -> tuple[str, str]:
    raw_token = secrets.token_urlsafe(32)

    return raw_token, sha256(raw_token)


def verify_token(raw_token: str, hashed_token: str) -> bool:
    return hmac.compare_digest(sha256(raw_token), hashed_token)
