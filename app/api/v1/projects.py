from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    ProjectAccess,
    get_current_user,
    get_project_access,
    get_workspace_member,
)
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.project import ProjectCreate, ProjectResponse, ProjectUpdate
from app.schemas.workspace import WorkspaceRole

router = APIRouter(tags=["Projects"])


@router.post(
    "/workspaces/{workspace_id}/projects",
    response_model=ProjectResponse,
    status_code=201,
)
async def create_project(
    workspace_id: int,
    data: ProjectCreate,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if member.role not in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
        raise ForbiddenException(ErrorMessages.FORBIDDEN)

    project = Project(
        workspace_id=workspace_id,
        name=data.name,
        description=data.description,
    )

    db.add(project)
    await db.commit()
    await db.refresh(project)

    return project


@router.get(
    "/workspaces/{workspace_id}/projects",
    response_model=list[ProjectResponse],
    dependencies=[Depends(get_workspace_member)],
)
async def list_projects(
    workspace_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
):
    query = (
        select(Project)
        .where(Project.workspace_id == workspace_id)
        .order_by(Project.created_at.desc())
    )

    result = await db.scalars(query)
    return result.all()


@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
)
@router.get(
    "/projects/{project_id}",
    response_model=ProjectResponse,
)
async def get_project(
    access: Annotated[ProjectAccess, Depends(get_project_access)],
):
    return access.project


@router.patch(
    "/projects/{project_id}",
    response_model=ProjectResponse,
)
async def update_project(
    project_id: int,
    data: ProjectUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    project = await db.get(Project, project_id)

    if project is None:
        raise NotFoundException(ErrorMessages.PROJECT_NOT_FOUND)

    member = await db.get(
        WorkspaceMember,
        (project.workspace_id, current_user.id),
    )

    if member is None:
        raise NotFoundException(ErrorMessages.PROJECT_NOT_FOUND)

    if member.role not in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
        raise ForbiddenException(ErrorMessages.FORBIDDEN)

    update_data = data.model_dump(exclude_unset=True)

    # name trong DB không cho phép NULL.
    # exclude_unset chỉ bỏ field không được gửi;
    # nó không tự loại bỏ name=null.
    if "name" in update_data and update_data["name"] is None:
        raise ValidationException(
            ErrorMessages.REQUIRED_FIELD_CANNOT_BE_NULL.format(field="name")
        )

    for key, value in update_data.items():
        setattr(project, key, value)

    await db.commit()
    await db.refresh(project)

    return project


@router.post(
    "/projects/{project_id}/archive",
    response_model=ProjectResponse,
)
async def archive_project(
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if access.member.role not in (
        WorkspaceRole.OWNER,
        WorkspaceRole.EDITOR,
    ):
        raise ForbiddenException(ErrorMessages.FORBIDDEN)

    access.project.status = ProjectStatus.ARCHIVED

    await db.commit()
    await db.refresh(access.project)

    return access.project
