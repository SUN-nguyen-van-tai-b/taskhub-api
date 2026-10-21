from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.project import ProjectStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)
    description: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    workspace_id: int
    name: str
    description: str | None
    status: ProjectStatus
    created_at: datetime


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=150)
    description: str | None = None
