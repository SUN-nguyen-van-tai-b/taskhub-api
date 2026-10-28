from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import (
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    VALIDATION_ERROR,
)
from app.core.dependencies import (
    ProjectAccess,
    TaskAccess,
    get_project_access,
    get_task_access,
)
from app.db.session import get_db
from app.models.task import TaskPriority, TaskStatus
from app.schemas.task import (
    TaskCreate,
    TaskFilters,
    TaskPage,
    TaskResponse,
    TaskUpdate,
)
from app.services.task_service import (
    create_task_service,
    delete_task_service,
    get_task_service,
    list_tasks_service,
    update_task_service,
)

router = APIRouter(
    tags=["Tasks"],
    responses={
        **UNAUTHORIZED,
        **FORBIDDEN,
        **NOT_FOUND,
        **CONFLICT,
        **VALIDATION_ERROR,
    },
)


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task",
)
async def create_task(
    project_id: int,
    data: TaskCreate,
    access: Annotated[
        ProjectAccess,
        Depends(get_project_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await create_task_service(
        db=db,
        data=data,
        access=access,
    )


@router.get(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Get task details",
)
async def get_task(
    access: Annotated[
        TaskAccess,
        Depends(get_task_access),
    ],
):
    return await get_task_service(access=access)


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskPage,
    summary="List and filter project tasks",
)
async def list_tasks(
    project_id: int,
    access: Annotated[
        ProjectAccess,
        Depends(get_project_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
    task_status: Annotated[
        TaskStatus | None,
        Query(alias="status"),
    ] = None,
    priority: TaskPriority | None = None,
    assignee_id: Annotated[
        int | None,
        Query(gt=0),
    ] = None,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 10,
):
    # Chuyển query params thành một object thống nhất.
    filters = TaskFilters(
        status=task_status,
        priority=priority,
        assignee_id=assignee_id,
    )

    return await list_tasks_service(
        db=db,
        access=access,
        filters=filters,
        page=page,
        page_size=page_size,
    )


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
)
async def update_task(
    data: TaskUpdate,
    access: Annotated[
        TaskAccess,
        Depends(get_task_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    return await update_task_service(
        db=db,
        data=data,
        access=access,
    )


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a task",
)
async def delete_task(
    access: Annotated[
        TaskAccess,
        Depends(get_task_access),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    await delete_task_service(
        db=db,
        access=access,
    )
