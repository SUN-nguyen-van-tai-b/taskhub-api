from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import (
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    VALIDATION_ERROR,
)
from app.core.dependencies import (
    CommentAccess,
    TaskAccess,
    get_comment_access,
    get_current_user,
    get_task_access,
)
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ForbiddenException,
    ValidationException,
)
from app.core.permissions import require_active_project, require_write_access
from app.db.session import get_db
from app.models.comment import Comment
from app.models.user import User
from app.models.workspace_member import WorkspaceRole
from app.schemas.comment import (
    CommentCreate,
    CommentPage,
    CommentResponse,
    CommentUpdate,
)

router = APIRouter(
    tags=["Comments"],
    responses={
        **UNAUTHORIZED,
        **FORBIDDEN,
        **NOT_FOUND,
        **CONFLICT,
        **VALIDATION_ERROR,
    },
)


def require_comment_edit_permission(
    comment: Comment,
    role: WorkspaceRole,
    current_user_id: int,
) -> None:
    # OWNER có quyền sửa/xóa mọi Comment.
    if role == WorkspaceRole.OWNER:
        return

    # EDITOR chỉ được sửa/xóa Comment do mình tạo.
    if role == WorkspaceRole.EDITOR and comment.created_by == current_user_id:
        return

    raise ForbiddenException(ErrorMessages.FORBIDDEN_COMMENT)


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task comment",
)
async def create_comment(
    data: CommentCreate,
    access: Annotated[TaskAccess, Depends(get_task_access)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_write_access(access.member.role)
    require_active_project(access.project)

    comment = Comment(
        task_id=access.task.id,
        created_by=current_user.id,
        content=data.content,
    )

    db.add(comment)
    await db.commit()
    await db.refresh(comment)

    return comment


@router.get(
    "/tasks/{task_id}/comments",
    response_model=CommentPage,
    summary="List comments on a task",
)
async def list_comments(
    access: Annotated[TaskAccess, Depends(get_task_access)],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=100)] = 20,
):
    total = (
        await db.scalar(
            select(func.count(Comment.id)).where(Comment.task_id == access.task.id)
        )
        or 0
    )

    offset = (page - 1) * page_size

    result = await db.scalars(
        select(Comment)
        .where(Comment.task_id == access.task.id)
        .order_by(Comment.created_at.asc(), Comment.id.asc())
        .offset(offset)
        .limit(page_size)
    )

    items = result.all()

    total_pages = (total + page_size - 1) // page_size

    return CommentPage(
        items=items,
        total=total,
        page=page,
        page_size=page_size,
        total_pages=total_pages,
    )


@router.patch(
    "/comments/{comment_id}",
    response_model=CommentResponse,
    summary="Update a comment",
)
async def update_comment(
    data: CommentUpdate,
    access: Annotated[CommentAccess, Depends(get_comment_access)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_comment_edit_permission(
        access.comment,
        access.member.role,
        current_user.id,
    )
    require_active_project(access.project)

    update_data = data.model_dump(exclude_unset=True)

    if "content" in update_data:
        content = update_data["content"]

        if content is None:
            raise ValidationException(ErrorMessages.COMMENT_CONTENT_REQUIRED)

        access.comment.content = content

        await db.commit()
        await db.refresh(access.comment)

    return access.comment


@router.delete(
    "/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_comment(
    access: Annotated[CommentAccess, Depends(get_comment_access)],
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    require_comment_edit_permission(
        access.comment,
        access.member.role,
        current_user.id,
    )
    require_active_project(access.project)

    await db.delete(access.comment)
    await db.commit()
