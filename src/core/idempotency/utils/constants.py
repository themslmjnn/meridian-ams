class HTTP409:
    IDEMPOTENCY_CONFLICT = (
        "A request with this idempotency key is already being processed"
    )
    IDEMPOTENCY_PAYLOAD_MISMATCH = (
        "This idempotency key was previously used with a different payload"
    )
    IDEMPOTENCY_REQUEST_IN_PROGRESS = (
        "A request with this key is currently being processed"
    )


class HTTP500:
    IDEMPOTENCY_STATE_ERROR = "Idempotency record in unexpected state"
