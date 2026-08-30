from datetime import datetime

from pydantic import BaseModel, EmailStr

from src.emails.utils.enums import EmailStatus, EmailType
from src.utils.base_schema import BaseSchema


class CreateEmail(BaseModel):
    recipient_email: EmailStr
    subject: str
    body_html: str
    email_type: EmailType
    triggered_by: int | None = None
    scheduled_for: datetime | None = None


class EmailResponseBase(BaseModel):
    recipient_email: str
    subject: str
    email_type: EmailType
    status: EmailStatus
    retry_count: int
    max_retries: int
    triggered_by: int | None


class EmailDetailResponse(EmailResponseBase, BaseSchema):
    id: int
    scheduled_for: datetime
    sent_at: datetime | None
    created_at: datetime
    last_error: str | None


class EmailFilters(BaseModel):
    status: EmailStatus | None = None
    email_type: EmailType | None = None
    triggered_by: int | None = None
    recipient_email: str | None = None
