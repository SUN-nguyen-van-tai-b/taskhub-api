from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator


class UserCreate(BaseModel):
    email: EmailStr
    full_name: str = Field(min_length=2, max_length=100)
    password: str = Field(min_length=8)


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    email: EmailStr
    full_name: str
    created_at: datetime


class UserUpdate(BaseModel):
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


class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str = Field(min_length=8)
