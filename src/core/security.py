import hashlib
import hmac
import secrets


def generate_activation_token() -> tuple[str, str]:
    raw_activation_token = secrets.token_urlsafe(32)
    hashed_activation_token = hashlib.sha256(raw_activation_token.encode()).hexdigest()

    return raw_activation_token, hashed_activation_token


def verify_activation_token(
    raw_activation_token: str, hashed_activation_token: str
) -> bool:
    return hmac.compare_digest(
        hashlib.sha256(raw_activation_token.encode()).hexdigest(),
        hashed_activation_token,
    )
