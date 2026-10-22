from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class LabelCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str = Field(min_length=1, max_length=100)

    color: str = Field(
        default="#6B7280",
        pattern=r"^#[0-9A-Fa-f]{6}$",
    )


class LabelUpdate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    name: str | None = Field(
        default=None,
        min_length=1,
        max_length=100,
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
