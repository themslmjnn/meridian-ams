import hashlib

NAMESPACE_PHONE_NUMBER = 9001
NAMESPACE_EMAIL = 9002
NAMESPACE_IDEMPOTENCY = 9003


def compute_lock_key(value: str) -> int:
    digest = hashlib.sha256(value.encode("utf-8")).digest()
    unsigned = int.from_bytes(digest[:4], byteorder="big", signed=False)

    return unsigned - 2**32 if unsigned >= 2**31 else unsigned
