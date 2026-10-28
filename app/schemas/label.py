from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MAX_LABEL_NAME_LENGTH
from app.schemas.base import BaseSchema


class LabelCreate(BaseSchema):
    name: str = Field(min_length=1, max_length=MAX_LABEL_NAME_LENGTH)

    color: str = Field(
        default="#6B7280",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class LabelUpdate(BaseSchema):
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_LABEL_NAME_LENGTH,
    )
    color: str | None = Field(
        default=None,
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class LabelResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    name: str
    color: str
    created_at: datetime
