from datetime import datetime

from pydantic import BaseModel

from src.emails.utils.enums import EmailStatus, EmailType
from src.utils.base_schema import BaseSchema


class EmailResponseBase(BaseModel):
    recipient_email: str
    subject: str
    email_type: EmailType
    status: EmailStatus
    retry_count: int
    max_retries: int
    triggered_by: int | None


class EmailResponseDetailed(EmailResponseBase, BaseSchema):
    id: int
    sent_at: datetime | None
    created_at: datetime
    last_error: str | None


class SearchEmail(BaseModel):
    status: EmailStatus | None = None
    email_type: EmailType | None = None
    triggered_by: int | None = None
    recipient_email: str | None = None
