import json
from hashlib import sha256
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    ProjectAccess,
    TaskAccess,
    get_project_access,
    get_task_access,
)
from app.core.redis_cache import (
    get_task_cache_version,
    invalidate_task_cache,
    read_task_cache,
    write_task_cache,
)
from app.db.session import get_db
from app.models.project import ProjectStatus
from app.models.task import Task, TaskPriority, TaskStatus
from app.models.user import User
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.task import TaskCreate, TaskPage, TaskResponse, TaskUpdate

router = APIRouter(tags=["Tasks"])


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_task(
    project_id: int,
    data: TaskCreate,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Kiểm tra người tạo có quyền ghi trong Workspace không.
    # VIEWER được xem và nhận Task nhưng không được tạo Task.
    if access.member.role not in (
        WorkspaceRole.OWNER,
        WorkspaceRole.EDITOR,
    ):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )

    # 2. Không cho tạo Task mới trong Project đã archive.
    # Vì Project ARCHIVED được xem là đã ngừng hoạt động.
    if access.project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(
            status_code=409,
            detail="Cannot create tasks in archived project",
        )

    # 3. Kiểm tra assignee_id nếu frontend truyền lên.
    if data.assignee_id is not None:
        assignee = await db.get(User, data.assignee_id)
        if assignee is None or not assignee.is_active:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="User invalid",
            )

        # TODO 3: Tìm WorkspaceMember bằng composite primary key:
        # (access.project.workspace_id, data.assignee_id).
        # Vì User có thể thuộc nhiều Workspace, nên phải kiểm tra
        # đúng Workspace chứa Project đang tạo Task.

        member = await db.get(
            WorkspaceMember,
            (access.project.workspace_id, data.assignee_id),
        )
        if member is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="User invalid",
            )

    # 4. Tạo Task.
    # project_id lấy từ URL; created_by lấy từ access.member.
    # Không cho frontend tự chọn người tạo Task.
    task = Task(
        project_id=project_id,
        title=data.title,
        description=data.description,
        assignee_id=data.assignee_id,
        priority=data.priority,
        due_date=data.due_date,
        created_by=access.member.user_id,
    )

    # 5. Đưa Task vào session để SQLAlchemy INSERT xuống PostgreSQL.
    db.add(task)

    # 6. Commit transaction để lưu Task.
    await db.commit()

    # 7. Đọc lại dữ liệu như id, created_at từ database.
    await db.refresh(task)

    await invalidate_task_cache(task.project_id)

    return task


@router.get("/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    access: Annotated[TaskAccess, Depends(get_task_access)],
):
    return access.task


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskPage,
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
    page: Annotated[
        int,
        Query(ge=1),
    ] = 1,
    page_size: Annotated[
        int,
        Query(ge=1, le=100),
    ] = 10,
):
    # Các bộ lọc phải được đưa vào key.
    # Hai request có status khác nhau không được dùng chung cache.
    filters = {
        "status": task_status.value if task_status is not None else None,
        "priority": priority.value if priority is not None else None,
        "assignee_id": assignee_id,
        "page": page,
        "page_size": page_size,
    }

    filters_json = json.dumps(
        filters,
        sort_keys=True,
    )

    filters_hash = sha256(filters_json.encode("utf-8")).hexdigest()

    version = await get_task_cache_version(project_id)

    cache_key = None

    if version is not None:
        cache_key = f"taskhub:tasks:project:{project_id}:v:{version}:{filters_hash}"

        cached_data = await read_task_cache(cache_key)

        if cached_data is not None:
            return TaskPage.model_validate(cached_data)

    query = select(Task).where(Task.project_id == project_id)

    if task_status is not None:
        query = query.where(Task.status == task_status)

    if priority is not None:
        query = query.where(Task.priority == priority)

    if assignee_id is not None:
        query = query.where(Task.assignee_id == assignee_id)

    # Phải đếm trước khi áp dụng LIMIT/OFFSET.
    # Nếu chỉ đếm Task trong trang hiện tại,
    # frontend không biết tổng cộng có bao nhiêu trang.
    count_query = select(func.count()).select_from(query.subquery())

    total = await db.scalar(count_query)
    total = total or 0
    # Page 1, size 10 -> offset 0
    # Page 2, size 10 -> offset 10
    # Page 3, size 10 -> offset 20
    offset = (page - 1) * page_size

    # ORDER BY created_at DESC để Task mới nằm trước.
    # Thêm id DESC để giữ thứ tự ổn định khi
    # nhiều Task có cùng created_at.
    query = (
        query.order_by(
            Task.created_at.desc(),
            Task.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    # scalars() trả về Task object trực tiếp,
    # thay vì các Row chứa Task.
    result = await db.scalars(query)
    tasks = result.all()

    # Ví dụ 21 Task / 10 Task mỗi trang = 3 trang.
    # Nếu không có Task, total_pages = 0.
    total_pages = (total + page_size - 1) // page_size

    response = TaskPage(
        items=list(tasks),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

    if cache_key is not None:
        # Kiểm tra version lần nữa để hạn chế ghi cache cũ
        # nếu Task vừa thay đổi trong lúc query.
        latest_version = await get_task_cache_version(project_id)

        if latest_version == version:
            await write_task_cache(
                cache_key,
                response.model_dump(mode="json"),
            )

    return response


@router.delete(
    "/tasks/{task_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_task(
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # VIEWER không được xóa Task.
    if access.member.role not in (
        WorkspaceRole.OWNER,
        WorkspaceRole.EDITOR,
    ):
        raise HTTPException(
            status_code=403,
            detail="Insufficient permissions",
        )

    # Task thuộc Project đã lưu trữ chỉ được xem.
    if access.project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(
            status_code=409,
            detail="Cannot modify tasks in archived project",
        )
    project_id = access.task.project_id

    await db.delete(access.task)
    await db.commit()

    await invalidate_task_cache(project_id)


@router.patch(
    "/tasks/{task_id}",
    response_model=TaskResponse,
)
async def update_task(
    task_id: int,
    data: TaskUpdate,
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    if access.member.role not in (
        WorkspaceRole.OWNER,
        WorkspaceRole.EDITOR,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Insufficient permissions",
        )

    if access.project.status == ProjectStatus.ARCHIVED:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot modify tasks in archived project",
        )

    update_data = data.model_dump(exclude_unset=True)

    required_fields = ("title", "status", "priority")

    for field in required_fields:
        if field in update_data and update_data[field] is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=f"{field} cannot be null",
            )

    if "assignee_id" in update_data:
        assignee_id = update_data["assignee_id"]

        if assignee_id is not None:
            assignee = await db.get(User, assignee_id)

            if assignee is None or not assignee.is_active:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Assignee does not exist or is inactive",
                )

            assignee_membership = await db.get(
                WorkspaceMember,
                (access.project.workspace_id, assignee_id),
            )

            if assignee_membership is None:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Assignee is not a member of this workspace",
                )

    for key, value in update_data.items():
        setattr(access.task, key, value)
    await db.commit()
    await db.refresh(access.task)

    await invalidate_task_cache(access.task.project_id)

    return access.task
