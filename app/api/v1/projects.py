from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import NOT_FOUND, UNAUTHORIZED, VALIDATION_ERROR
from app.core.dependencies import (
    ProjectAccess,
    get_project_access,
    get_workspace_member,
)
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ForbiddenException,
    ValidationException,
)
from app.core.pagination import Pagination
from app.core.permissions import require_write_access
from app.db.session import get_db
from app.models.project import Project, ProjectStatus
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

    require_write_access(member.role)

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
    summary="List projects in a workspace",
    responses={
        **UNAUTHORIZED,
        **NOT_FOUND,
        **VALIDATION_ERROR,
    },
)
async def list_projects(
    workspace_id: int,
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Pagination,
) -> list[Project]:
    query = (
        select(Project)
        .where(Project.workspace_id == workspace_id)
        .order_by(
            Project.created_at.desc(),
            Project.id.desc(),
        )
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )

    result = await db.scalars(query)
    return list(result.all())


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
    data: ProjectUpdate,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> Project:
    project = access.project

    require_write_access(access.member.role)

    update_data = data.model_dump(exclude_unset=True)

    # Không cho phép name = null.
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
