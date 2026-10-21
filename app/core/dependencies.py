from dataclasses import dataclass
from typing import Annotated

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_token
from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.workspace_member import WorkspaceMember

bearer_scheme = HTTPBearer(auto_error=False)


async def get_current_user(
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Depends(bearer_scheme),
    ],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Kiểm tra credentials có tồn tại không
    if credentials is None:
        raise credentials_exception

    # 2. Lấy Access Token từ credentials.credentials
    access_token = credentials.credentials

    # 3. Decode token và bắt jwt.InvalidTokenError
    try:
        payload = decode_token(access_token)
    except jwt.InvalidTokenError as exc:
        raise credentials_exception from exc

    # 4. Kiểm tra type == "access"
    if payload.get("type") != "access":
        raise credentials_exception

    # 5. Validate sub là chuỗi số hợp lệ
    user_id = payload.get("sub")
    if not isinstance(user_id, str) or not user_id.isdecimal():
        raise credentials_exception

    # 6. Truy vấn await db.get(User, int(user_id))
    user = await db.get(User, int(user_id))

    # 7. Kiểm tra user tồn tại và is_active
    if user is None or not user.is_active:
        raise credentials_exception

    # 8. Return user
    return user


async def get_workspace_member(
    workspace_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> WorkspaceMember:
    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )

    return member


# chúng ta muốn một dependency trả về hai object có tên thuộc tính rõ ràng, nên dùng dataclass
@dataclass
class ProjectAccess:
    project: Project
    member: WorkspaceMember


async def get_project_access(
    project_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> ProjectAccess:
    # 1. Tìm Project trước vì URL chỉ chứa project_id.
    # Nếu không tìm thấy, không thể xác định Workspace.
    project = await db.get(Project, project_id)

    if project is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    # 2. Dùng workspace_id từ Project để kiểm tra membership.
    # Không phải thành viên thì không được truy cập Project.
    member = await db.get(
        WorkspaceMember,
        (project.workspace_id, current_user.id),
    )

    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Project not found",
        )

    # 3. Trả cả hai object.
    # Endpoint dùng project để xử lý dữ liệu,
    # member để kiểm tra quyền OWNER/EDITOR/VIEWER.
    return ProjectAccess(project=project, member=member)


@dataclass
class TaskAccess:
    task: Task
    project: Project
    member: WorkspaceMember


async def get_task_access(
    task_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TaskAccess:
    # Tìm Task để biết nó thuộc Project nào.
    task = await db.get(Task, task_id)

    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Tìm Project để lấy workspace_id.
    project = await db.get(Project, task.project_id)

    if project is None:
        raise HTTPException(status_code=404, detail="Task not found")

    # Xác nhận người đang đăng nhập thuộc Workspace chứa Task.
    member = await db.get(
        WorkspaceMember,
        (project.workspace_id, current_user.id),
    )

    if member is None:
        raise HTTPException(status_code=404, detail="Task not found")

    return TaskAccess(task=task, project=project, member=member)
