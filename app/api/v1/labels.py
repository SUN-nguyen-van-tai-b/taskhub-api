from dataclasses import dataclass
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    ProjectAccess,
    TaskAccess,
    get_current_user,
    get_project_access,
    get_task_access,
)
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.db.session import get_db
from app.models.label import Label
from app.models.project import Project, ProjectStatus
from app.models.task_label import TaskLabel
from app.models.user import User
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.label import LabelCreate, LabelResponse, LabelUpdate

router = APIRouter(tags=["Labels"])


def require_label_write_access(role: WorkspaceRole) -> None:
    # Tách logic kiểm tra quyền thành một hàm dùng chung.
    # OWNER/EDITOR được chỉnh sửa Labels, VIEWER chỉ được xem.
    if role not in (WorkspaceRole.OWNER, WorkspaceRole.EDITOR):
        raise ForbiddenException(ErrorMessages.FORBIDDEN)


def require_active_project(project: Project) -> None:
    # Project đã archive chỉ cho đọc dữ liệu.
    if project.status == ProjectStatus.ARCHIVED:
        raise ConflictException(ErrorMessages.PROJECT_ARCHIVED)


@dataclass
class LabelAccess:
    label: Label
    project: Project
    member: WorkspaceMember


async def get_label_access(
    label_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> LabelAccess:

    # Lấy cả 3 ORM object từ một truy vấn.
    query = (
        select(Label, Project, WorkspaceMember)
        .join(Project, Label.project_id == Project.id)
        .join(
            WorkspaceMember,
            WorkspaceMember.workspace_id == Project.workspace_id,
        )
        .where(
            Label.id == label_id,
            WorkspaceMember.user_id == current_user.id,
        )
    )

    result = await db.execute(query)
    row = result.one_or_none()

    if row is None:
        raise NotFoundException(ErrorMessages.LABEL_NOT_FOUND)

    # row[0] = Label
    # row[1] = Project
    # row[2] = WorkspaceMember
    return LabelAccess(
        label=row[0],
        project=row[1],
        member=row[2],
    )


@router.post(
    "/projects/{project_id}/labels",
    response_model=LabelResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_label(
    project_id: int,
    data: LabelCreate,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_label_write_access(access.member.role)
    require_active_project(access.project)

    # Kiểm tra trùng tên để trả lỗi dễ hiểu.
    existing = await db.scalar(
        select(Label).where(
            Label.project_id == project_id,
            Label.name == data.name,
        )
    )
    if existing is not None:
        raise ConflictException(ErrorMessages.LABEL_ALREADY_EXISTS)

    label = Label(
        project_id=project_id,
        name=data.name,
        color=data.color,
    )
    db.add(label)

    try:
        await db.commit()
    except IntegrityError as exc:
        # UniqueConstraint bảo vệ cả trường hợp hai request
        # cùng tạo Label trùng tên gần như đồng thời.
        await db.rollback()
        raise ConflictException(ErrorMessages.LABEL_CREATE_CONFLICT) from exc

    await db.refresh(label)
    return label


@router.get(
    "/projects/{project_id}/labels",
    response_model=list[LabelResponse],
)
async def list_labels(
    project_id: int,
    access: Annotated[ProjectAccess, Depends(get_project_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # OWNER/EDITOR/VIEWER đều được xem.
    # Chỉ lấy Label thuộc Project đang truy cập.
    result = await db.scalars(
        select(Label)
        .where(Label.project_id == project_id)
        .order_by(Label.name.asc(), Label.id.asc())
    )
    return result.all()


@router.patch(
    "/labels/{label_id}",
    response_model=LabelResponse,
)
async def update_label(
    data: LabelUpdate,
    access: Annotated[LabelAccess, Depends(get_label_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_label_write_access(access.member.role)
    require_active_project(access.project)

    # Không gửi field -> giữ nguyên.
    # Gửi null -> từ chối vì DB yêu cầu NOT NULL.
    update_data = data.model_dump(exclude_unset=True)

    for key, value in update_data.items():
        if value is None:
            raise ValidationException(
                ErrorMessages.REQUIRED_FIELD_CANNOT_BE_NULL.format(field=key)
            )
        setattr(access.label, key, value)

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(ErrorMessages.LABEL_UPDATE_CONFLICT) from exc
    await db.refresh(access.label)
    return access.label


# 4. DELETE LABEL
@router.delete(
    "/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_label(
    access: Annotated[LabelAccess, Depends(get_label_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_label_write_access(access.member.role)
    require_active_project(access.project)

    # FK ondelete=CASCADE xóa các dòng task_labels
    # liên quan đến Label này, nhưng giữ nguyên Task.
    await db.delete(access.label)
    await db.commit()


# 5. ATTACH LABEL TO TASK
@router.post(
    "/tasks/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def attach_label_to_task(
    label_id: int,
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_label_write_access(access.member.role)
    require_active_project(access.project)

    label = await db.get(Label, label_id)

    # Kiểm tra Label cùng Project với Task.
    # Đây là phần quan trọng để ngăn liên kết chéo Project.
    if label is None or label.project_id != access.task.project_id:
        raise NotFoundException(ErrorMessages.LABEL_NOT_FOUND_IN_PROJECT)

    # Composite PK ngăn gắn trùng một Label vào cùng Task.
    existing = await db.get(
        TaskLabel,
        (access.task.id, label_id),
    )
    if existing is not None:
        raise ConflictException(ErrorMessages.LABEL_ALREADY_ATTACHED)

    db.add(TaskLabel(task_id=access.task.id, label_id=label_id))

    try:
        await db.commit()
    except IntegrityError as exc:
        await db.rollback()
        raise ConflictException(ErrorMessages.LABEL_ATTACH_CONFLICT) from exc


# 6. DETACH LABEL FROM TASK
@router.delete(
    "/tasks/{task_id}/labels/{label_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def detach_label_from_task(
    label_id: int,
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_label_write_access(access.member.role)
    require_active_project(access.project)

    # Chỉ xóa liên kết, không xóa bản ghi Label.
    task_label = await db.get(
        TaskLabel,
        (access.task.id, label_id),
    )
    if task_label is None:
        raise NotFoundException(ErrorMessages.TASK_LABEL_ASSOCIATION_NOT_FOUND)

    await db.delete(task_label)
    await db.commit()


# 7. LIST LABELS OF TASK
@router.get(
    "/tasks/{task_id}/labels",
    response_model=list[LabelResponse],
)
async def list_task_labels(
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Dùng JOIN để lấy Label thông qua bảng task_labels.
    # Không cần khai báo relationship ORM cho trường hợp này.
    result = await db.scalars(
        select(Label)
        .join(TaskLabel, TaskLabel.label_id == Label.id)
        .where(
            TaskLabel.task_id == access.task.id,
            Label.project_id == access.task.project_id,
        )
        .order_by(Label.name.asc(), Label.id.asc())
    )
    return result.all()
