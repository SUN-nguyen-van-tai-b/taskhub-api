from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.workspace_member import WorkspaceRole


class WorkspaceCreate(BaseModel):
    name: str = Field(min_length=2, max_length=150)


class WorkspaceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    owner_id: int
    created_at: datetime


class WorkspaceUpdate(BaseModel):
    name: str = Field(min_length=2, max_length=150)


class WorkspaceMemberCreate(BaseModel):
    user_id: int = Field(gt=0)
    role: WorkspaceRole


class WorkspaceMemberResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    workspace_id: int
    user_id: int
    role: WorkspaceRole


class WorkspaceMemberRoleUpdate(BaseModel):
    role: WorkspaceRole
