from meridian_ams.core.exceptions import AppException


# HTTP409
class IdempotencyConflict(AppException):
    status_code = 409
    detail = "A request with this idempotency key is already being processed"
    error_code = "IDEMPOTENCY_CONFLICT"


class IdempotencyRequestInProgress(AppException):
    status_code = 409
    detail = "This idempotency key was previously used with a different payload"
    error_code = "IDEMPOTENCY_REQUEST_IN_PROGRESS"


class IdempotencyPayloadMismatch(AppException):
    status_code = 409
    detail = "A request with this key is currently being processed"
    error_code = "IDEMPOTENCY_PAYLOAD_MISMATCH"


# HTTP500
class IdempotencyStateError(AppException):
    status_code = 500
    detail = "Idempotency record in unexpected state"
    error_code = "IDEMPOTENCY_STATE_ERROR"
