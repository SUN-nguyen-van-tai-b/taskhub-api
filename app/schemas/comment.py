from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.base import BaseSchema


class CommentCreate(BaseSchema):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(
        min_length=1,
        max_length=5000,
    )


class CommentUpdate(BaseSchema):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Không gửi content -> không thay đổi.
    # Gửi null -> endpoint từ chối.
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=5000,
    )


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    created_by: int
    content: str
    created_at: datetime
    updated_at: datetime


class CommentPage(BaseModel):
    items: list[CommentResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
