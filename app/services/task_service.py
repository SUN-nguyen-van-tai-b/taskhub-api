import json
import logging
from hashlib import sha256

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import ProjectAccess, TaskAccess
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ValidationException,
)
from app.core.permissions import require_active_project, require_write_access
from app.core.redis_cache import (
    get_task_cache_version,
    invalidate_task_cache,
    read_task_cache,
    write_task_cache,
)
from app.models.task import Task
from app.models.user import User
from app.models.workspace_member import WorkspaceMember
from app.schemas.task import (
    TaskCreate,
    TaskFilters,
    TaskPage,
    TaskUpdate,
)

logger = logging.getLogger(__name__)


async def validate_assignee(
    db: AsyncSession,
    workspace_id: int,
    assignee_id: int | None,
) -> None:
    # None nghĩa là Task chưa được giao cho ai.
    if assignee_id is None:
        return

    # User phải tồn tại và đang hoạt động.
    assignee = await db.get(User, assignee_id)

    if assignee is None or not assignee.is_active:
        raise ValidationException(ErrorMessages.ASSIGNEE_NOT_FOUND_OR_INACTIVE)

    # User phải thuộc đúng Workspace chứa Task.
    member = await db.get(
        WorkspaceMember,
        (workspace_id, assignee_id),
    )

    if member is None:
        raise ValidationException(ErrorMessages.ASSIGNEE_NOT_WORKSPACE_MEMBER)


async def create_task_service(
    db: AsyncSession,
    data: TaskCreate,
    access: ProjectAccess,
) -> Task:
    require_write_access(access.member.role)
    require_active_project(access.project)

    await validate_assignee(
        db=db,
        workspace_id=access.project.workspace_id,
        assignee_id=data.assignee_id,
    )

    task = Task(
        project_id=access.project.id,
        title=data.title,
        description=data.description,
        assignee_id=data.assignee_id,
        priority=data.priority,
        due_date=data.due_date,
        created_by=access.member.user_id,
    )

    db.add(task)
    await db.commit()
    await db.refresh(task)

    # Task mới phải xuất hiện trong danh sách GET.
    await invalidate_task_cache(task.project_id)

    logger.info("Task created | task_id=%s", task.id)

    return task


async def get_task_service(
    access: TaskAccess,
) -> Task:
    # get_task_access() đã kiểm tra:
    # Task -> Project -> WorkspaceMember -> Current User.
    return access.task


async def list_tasks_service(
    db: AsyncSession,
    access: ProjectAccess,
    filters: TaskFilters,
    page: int,
    page_size: int,
) -> TaskPage:
    project_id = access.project.id

    # Chuẩn hóa filters để tạo cache key.
    filter_data = {
        "status": (filters.status.value if filters.status is not None else None),
        "priority": (filters.priority.value if filters.priority is not None else None),
        "assignee_id": filters.assignee_id,
        "page": page,
        "page_size": page_size,
    }

    filters_json = json.dumps(
        filter_data,
        sort_keys=True,
    )

    filters_hash = sha256(filters_json.encode("utf-8")).hexdigest()

    # Đọc version của Project từ Redis.
    version = await get_task_cache_version(project_id)

    cache_key = None

    if version is not None:
        cache_key = f"taskhub:tasks:project:{project_id}:v:{version}:{filters_hash}"

        cached_data = await read_task_cache(cache_key)

        if cached_data is not None:
            logger.info(
                "CACHE HIT | project_id=%s | page=%s",
                project_id,
                page,
            )

            return TaskPage.model_validate(cached_data)

    logger.info(
        "CACHE MISS | project_id=%s | page=%s",
        project_id,
        page,
    )

    # Cache MISS -> truy vấn PostgreSQL.
    query = select(Task).where(Task.project_id == project_id)

    if filters.status is not None:
        query = query.where(Task.status == filters.status)

    if filters.priority is not None:
        query = query.where(Task.priority == filters.priority)

    if filters.assignee_id is not None:
        query = query.where(Task.assignee_id == filters.assignee_id)

    # COUNT phải tính trước LIMIT/OFFSET.
    count_query = select(func.count()).select_from(query.subquery())

    total = await db.scalar(count_query) or 0

    offset = (page - 1) * page_size

    query = (
        query.order_by(
            Task.created_at.desc(),
            Task.id.desc(),
        )
        .offset(offset)
        .limit(page_size)
    )

    result = await db.scalars(query)
    tasks = result.all()

    total_pages = (total + page_size - 1) // page_size

    response = TaskPage(
        items=list(tasks),
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )

    # Lưu Cache sau khi query DB.
    # Kiểm tra version thêm lần nữa để giảm khả năng
    # ghi dữ liệu cũ trong lúc Task bị thay đổi.
    if cache_key is not None:
        latest_version = await get_task_cache_version(project_id)

        if latest_version == version:
            await write_task_cache(
                cache_key,
                response.model_dump(mode="json"),
            )

            logger.info(
                "CACHE WRITE | project_id=%s | page=%s",
                project_id,
                page,
            )

    return response


async def update_task_service(
    db: AsyncSession,
    data: TaskUpdate,
    access: TaskAccess,
) -> Task:
    require_write_access(access.member.role)
    require_active_project(access.project)

    # PATCH: chỉ lấy những field frontend đã gửi.
    update_data = data.model_dump(exclude_unset=True)

    # Các trường NOT NULL không được nhận null.
    required_fields = ("title", "status", "priority")

    for field in required_fields:
        if field in update_data and update_data[field] is None:
            raise ValidationException(
                ErrorMessages.REQUIRED_FIELD_CANNOT_BE_NULL.format(field=field)
            )

    # Nếu frontend muốn đổi assignee, phải kiểm tra lại
    # User có hợp lệ và thuộc Workspace hay không.
    if "assignee_id" in update_data:
        await validate_assignee(
            db=db,
            workspace_id=access.project.workspace_id,
            assignee_id=update_data["assignee_id"],
        )

    # Không có field thay đổi thì không cần commit.
    if not update_data:
        return access.task

    # TaskUpdate phải chỉ khai báo những field được phép sửa.
    # Không đưa id, project_id, created_by vào TaskUpdate.
    for key, value in update_data.items():
        setattr(access.task, key, value)

    await db.commit()
    await db.refresh(access.task)

    # Update có thể ảnh hưởng danh sách và bộ lọc Task.
    await invalidate_task_cache(access.task.project_id)

    logger.info(
        "Task updated | task_id=%s",
        access.task.id,
    )

    return access.task


async def delete_task_service(
    db: AsyncSession,
    access: TaskAccess,
) -> None:
    # Chỉ OWNER/EDITOR được xóa.
    require_write_access(access.member.role)

    # Không được xóa Task trong Project ARCHIVED.
    require_active_project(access.project)

    # Lưu ID để invalidate cache sau khi xóa.
    project_id = access.task.project_id

    await db.delete(access.task)
    await db.commit()

    # Xóa hiệu lực cache danh sách Task của Project.
    await invalidate_task_cache(project_id)
