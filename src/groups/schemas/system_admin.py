import uuid
from datetime import datetime

from pydantic import BaseModel, Field, field_validator

from src.groups.utils.validators import validate_academic_year
from src.utils.base_schema import BaseSchema


class GroupResponseBase(BaseSchema):
    public_id: uuid.UUID
    name: str
    academic_year: str
    grade_level: int


class GroupResponseAdminDetailed(GroupResponseBase):
    max_capacity: int
    student_count: int
    is_archived: bool
    archived_at: datetime | None
    created_at: datetime
    updated_at: datetime


class CreateGroupAdmin(BaseModel):
    name: str = Field(min_length=1, max_length=20)
    academic_year: str = Field(pattern=r"^\d{4}-\d{4}$")
    grade_level: int = Field(ge=1, le=12)
    max_capacity: int = Field(gt=0, default=30)

    @field_validator("academic_year")
    @classmethod
    def _validate_academic_year(cls, v: str) -> str:
        return validate_academic_year(v)
