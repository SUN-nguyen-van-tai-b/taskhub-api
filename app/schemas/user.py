from datetime import datetime

from pydantic import (
    BaseModel,
    ConfigDict,
    EmailStr,
    Field,
    field_validator,
    model_validator,
)

from app.core.constants import MAX_PASSWORD_LENGTH
from app.schemas.base import BaseSchema


class UserCreate(BaseSchema):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)

    @field_validator("email", mode="after")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        return value.strip().lower()

    @field_validator("full_name", mode="before")
    @classmethod
    def normalize_full_name(cls, value: str) -> str:
        return value.strip() if isinstance(value, str) else value


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    created_at: datetime


class UserUpdate(BaseSchema):
    full_name: str | None = Field(
        default=None,
        min_length=2,
        max_length=100,
    )

    @model_validator(mode="after")
    def validate_full_name(self):
        if "full_name" in self.model_fields_set and self.full_name is None:
            raise ValueError("full_name cannot be null")

        return self


class ChangePasswordRequest(BaseSchema):
    old_password: str
    new_password: str = Field(min_length=8, max_length=MAX_PASSWORD_LENGTH)
