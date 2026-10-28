from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.core.constants import MAX_CONTENT_COMMENT_LENGTH
from app.schemas.base import BaseSchema, PageSchema


class CommentCreate(BaseSchema):
    model_config = ConfigDict(str_strip_whitespace=True)

    content: str = Field(
        min_length=1,
        max_length=MAX_CONTENT_COMMENT_LENGTH,
    )


class CommentUpdate(BaseSchema):
    model_config = ConfigDict(str_strip_whitespace=True)

    # Không gửi content -> không thay đổi.
    # Gửi null -> endpoint từ chối.
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=MAX_CONTENT_COMMENT_LENGTH,
    )


class CommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_id: int
    created_by: int
    content: str
    created_at: datetime
    updated_at: datetime


class CommentPage(PageSchema[CommentResponse]):
    pass
