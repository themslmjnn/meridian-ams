from enum import StrEnum


class IdempotencyStatus(StrEnum):
    PROCESSING = "processing"
    COMPLETE = "complete"
