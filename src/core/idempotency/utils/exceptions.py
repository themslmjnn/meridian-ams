from src.core.exceptions import AppException
from src.core.idempotency.utils.constants import HTTP409, HTTP500


# HTTP409
class IdempotencyConflict(AppException):
    status_code = 409
    detail = HTTP409.IDEMPOTENCY_CONFLICT
    error_code = "IDEMPOTENCY_CONFLICT"


class IdempotencyRequestInProgress(AppException):
    status_code = 409
    detail = HTTP409.IDEMPOTENCY_REQUEST_IN_PROGRESS
    error_code = "IDEMPOTENCY_REQUEST_IN_PROGRESS"


class IdempotencyPayloadMismatch(AppException):
    status_code = 409
    detail = HTTP409.IDEMPOTENCY_PAYLOAD_MISMATCH
    error_code = "IDEMPOTENCY_PAYLOAD_MISMATCH"


# HTTP500
class IdempotencyStateError(AppException):
    status_code = 500
    detail = HTTP500.IDEMPOTENCY_STATE_ERROR
    error_code = "IDEMPOTENCY_STATE_ERROR"
