from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy import delete, exists, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.api_responses import (
    BAD_REQUEST,
    CONFLICT,
    FORBIDDEN,
    NOT_FOUND,
    UNAUTHORIZED,
    VALIDATION_ERROR,
)
from app.core.dependencies import get_current_user, get_workspace_member
from app.core.enums import WorkspaceRole
from app.core.error_messages import ErrorMessages
from app.core.exceptions import (
    ConflictException,
    ForbiddenException,
    NotFoundException,
    ValidationException,
)
from app.core.pagination import Pagination
from app.core.redis_cache import (
    invalidate_task_cache,
)
from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember
from app.schemas.base import PageSchema
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter(
    prefix="/workspaces",
    tags=["Workspaces"],
    responses={
        **BAD_REQUEST,
        **CONFLICT,
        **FORBIDDEN,
        **NOT_FOUND,
        **UNAUTHORIZED,
        **VALIDATION_ERROR,
    },
)


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a workspace",
)
async def create_workspace(
    data: WorkspaceCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tạo Workspace và gán user đang đăng nhập làm chủ sở hữu.
    # Không nhận owner_id từ frontend để tránh người dùng
    # tự ý tạo Workspace dưới tên người khác.
    workspace = Workspace(
        name=data.name,
        owner_id=current_user.id,
    )

    # 2. Đưa Workspace vào session của SQLAlchemy.
    # Lúc này chưa đảm bảo INSERT đã được gửi tới database.
    db.add(workspace)

    # 3. Gửi INSERT xuống database để PostgreSQL cấp ID.
    # Ta cần workspace.id để tạo membership liên kết đúng Workspace.
    # flush() chưa commit nên cả hai thao tác vẫn trong một transaction.
    await db.flush()

    # 4. Tự động thêm người tạo vào danh sách thành viên với role OWNER.
    # workspace_id là khóa ngoại trỏ đến Workspace vừa được tạo.
    member = WorkspaceMember(
        workspace_id=workspace.id,
        user_id=current_user.id,
        role=WorkspaceRole.OWNER,
    )

    # 5. Đưa membership vào session.
    # SQLAlchemy sẽ INSERT bản ghi này khi flush/commit.
    db.add(member)

    # 6. Commit toàn bộ transaction.
    # Nếu thành công, cả Workspace và membership được lưu.
    await db.commit()

    # 7. Đồng bộ lại dữ liệu Workspace từ database,
    # bao gồ mnhững giá trị được DB tạo như created_at.
    await db.refresh(workspace)

    # 8. Trả ORM object.
    # FastAPI sử dụng WorkspaceResponse để serialize ra JSON.
    return workspace


@router.get(
    "",
    response_model=PageSchema[WorkspaceResponse],
    summary="List the current user's workspaces",
)
async def list_workspaces(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Pagination,
):
    filters = WorkspaceMember.user_id == current_user.id
    total = (
        await db.scalar(
            select(func.count(Workspace.id))
            .join(WorkspaceMember, Workspace.id == WorkspaceMember.workspace_id)
            .where(filters)
        )
        or 0
    )

    query = (
        select(Workspace)
        .join(
            WorkspaceMember,
            Workspace.id == WorkspaceMember.workspace_id,
        )
        .where(filters)
        .order_by(Workspace.created_at.desc(), Workspace.id.desc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.scalars(query)
    return PageSchema[WorkspaceResponse](
        items=list(result.all()),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages(total),
    )


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Get workspace details",
)
async def get_workspace(
    workspace_id: int,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Bước 1: Tìm Workspace theo workspace_id.
    # Cần kiểm tra bản ghi có tồn tại trước khi trả dữ liệu.
    # Nếu không tồn tại, trả HTTP 404.
    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_NOT_FOUND)

    # Bước 2: Kiểm tra WorkspaceMember với:
    # workspace_id = workspace_id
    # user_id = current_user.id
    # Vì biết workspace_id chưa có nghĩa user được phép xem nó.

    return workspace


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
    summary="Update a workspace",
)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm Workspace theo ID.
    # Cần xác nhận Workspace tồn tại trước khi cập nhật.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_NOT_FOUND)

    # 2. Nếu member.role != WorkspaceRole.OWNER, trả HTTP 403.
    # Chỉ OWNER mới được phép đổi tên Workspace.

    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.ONLY_OWNER_CAN_UPDATE_WORKSPACE)

    # 3. Gán tên mới từ data.name vào workspace.name.
    # SQLAlchemy theo dõi thay đổi trên ORM object.
    workspace.name = data.name

    # 4. await db.commit().
    # Lưu thay đổi vào PostgreSQL.
    await db.commit()

    # 5. await db.refresh(workspace).
    # Đồng bộ object với dữ liệu đã lưu trong database.
    await db.refresh(workspace)

    # 6. Trả về Workspace.
    return workspace


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a workspace",
)
async def delete_workspace(
    workspace_id: int,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm Workspace theo workspace_id.
    # Cần biết Workspace có tồn tại trước khi xử lý xóa.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_NOT_FOUND)

    # 2. Kiểm tra member.role có phải OWNER không.
    # Chỉ OWNER có quyền xóa toàn bộ Workspace.
    # Nếu không đủ quyền thì trả 403.

    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.ONLY_OWNER_CAN_DELETE_WORKSPACE)

    # 3. Kiểm tra Workspace còn Project hay không.
    # Nếu còn Project thì trả 409, tránh lỗi Foreign Key.

    has_projects = await db.scalar(
        select(exists().where(Project.workspace_id == workspace_id))
    )

    if has_projects:
        raise ConflictException(ErrorMessages.WORKSPACE_HAS_PROJECTS)

    # 4. Xóa Workspace bằng await db.delete(workspace).
    # AsyncSession.delete() là coroutine nên phải await.
    try:
        await db.execute(
            delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )

        await db.delete(workspace)
        await db.commit()

    except IntegrityError as exc:
        await db.rollback()

        raise ConflictException(ErrorMessages.WORKSPACE_DELETE_CONFLICT) from exc


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkspaceMemberResponse,
    summary="Add a workspace member",
)
async def add_workspace_member(
    workspace_id: int,
    data: WorkspaceMemberCreate,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Bước 1: Tìm Workspace theo workspace_id.
    # Tại sao? Chúng ta không thể thêm thành viên vào
    # một Workspace không tồn tại. Nếu không tìm thấy → 404.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_NOT_FOUND)

    # Bước 2: Tìm membership của current_user.
    # Tại sao? Đăng nhập thành công không đồng nghĩa
    # với việc có quyền quản lý mọi Workspace.
    # Nếu không thuộc Workspace → 404.

    # Bước 3: Kiểm tra current_user có role OWNER không.
    # Tại sao? Chỉ OWNER mới được phép quản lý thành viên.
    # EDITOR và VIEWER phải nhận HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.ONLY_OWNER_CAN_ADD_WORKSPACE_MEMBERS)

    # Bước 4: Kiểm tra data.role không phải OWNER.
    # Tại sao? Không cho phép một người thêm OWNER mới
    # thông qua endpoint này. Nếu vi phạm → 422.

    if data.role == WorkspaceRole.OWNER:
        raise ValidationException(ErrorMessages.CANNOT_ASSIGN_OWNER_ROLE)

    # Bước 5: Tìm User cần thêm bằng data.user_id.
    # Tại sao? user_id phải tham chiếu đến User tồn tại.
    # Nên kiểm tra is_active để không mời tài khoản bị khóa.
    user = await db.get(User, data.user_id)
    if user is None or not user.is_active:
        raise NotFoundException(ErrorMessages.USER_NOT_FOUND)
    # Bước 6: Kiểm tra User đã là thành viên chưa.
    # Dùng db.get(WorkspaceMember, (workspace_id, data.user_id)).
    # Tại sao? Composite primary key không cho phép
    # thêm hai membership trùng Workspace + User.
    # Nếu đã là thành viên → HTTP 409.
    existing_member = await db.get(
        WorkspaceMember,
        (workspace_id, data.user_id),
    )
    if existing_member is not None:
        raise ConflictException(ErrorMessages.USER_ALREADY_WORKSPACE_MEMBER)

    # Bước 7: Tạo WorkspaceMember và db.add().
    # Tại sao? Đây là bản ghi liên kết User với Workspace,
    # đồng thời lưu vai trò OWNER/EDITOR/VIEWER.
    member = WorkspaceMember(
        workspace_id=workspace.id, user_id=data.user_id, role=data.role
    )

    db.add(member)

    # Bước 8: await db.commit().
    # Tại sao? Để PostgreSQL xác nhận bản ghi membership.
    await db.commit()
    # Bước 9: Trả thông tin thành viên vừa thêm.
    return member


@router.get(
    "/{workspace_id}/members",
    response_model=PageSchema[WorkspaceMemberResponse],
    summary="List workspace members",
)
async def list_workspace_members(
    workspace_id: int,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
    pagination: Pagination,
):
    # 1. Kiểm tra current_user có membership trong Workspace không.
    # Vì API chỉ dành cho thành viên của Workspace.
    # Nếu không có membership, trả 404 để tránh lộ thông tin.
    total = (
        await db.scalar(
            select(func.count(WorkspaceMember.user_id)).where(
                WorkspaceMember.workspace_id == workspace_id
            )
        )
        or 0
    )
    query = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
    query = (
        query.order_by(WorkspaceMember.user_id.asc())
        .offset(pagination.offset)
        .limit(pagination.page_size)
    )
    result = await db.scalars(query)
    return PageSchema[WorkspaceMemberResponse](
        items=list(result.all()),
        total=total,
        page=pagination.page,
        page_size=pagination.page_size,
        total_pages=pagination.total_pages(total),
    )


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a workspace member",
)
async def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Kiểm tra membership của người đang đăng nhập.
    # Vì chỉ người thuộc Workspace mới có thể quản lý thành viên.
    # Nếu không tìm thấy, trả HTTP 404.

    # 2. Kiểm tra current_user có role OWNER không.
    # Vì EDITOR và VIEWER không có quyền xóa thành viên.
    # Nếu không phải OWNER, trả HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.ONLY_OWNER_CAN_DELETE_MEMBERS)

    # 3. Tìm WorkspaceMember cần xóa bằng (workspace_id, user_id).
    # Vì phải xác định chính xác người cần xóa trong Workspace này.
    # Nếu không tìm thấy, trả HTTP 404.

    target_member = await db.get(
        WorkspaceMember,
        (workspace_id, user_id),
    )
    if target_member is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_MEMBER_NOT_FOUND)

    # 4. Không cho phép xóa OWNER.
    # Vì Workspace phải luôn có một OWNER theo thiết kế hiện tại.
    # Nếu thành viên cần xóa là OWNER, trả HTTP 403.
    if target_member.role == WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.CANNOT_REMOVE_OWNER_MEMBER)

    # Lấy danh sách Project có Task đang assign cho user.
    result = await db.scalars(
        select(Task.project_id)
        .join(Project, Task.project_id == Project.id)
        .where(
            Project.workspace_id == workspace_id,
            Task.assignee_id == user_id,
        )
        .distinct()
    )

    affected_project_ids = result.all()

    # Unassign Task của member trong Workspace.
    await db.execute(
        update(Task)
        .where(
            Task.assignee_id == user_id,
            Task.project_id.in_(affected_project_ids),
        )
        .values(assignee_id=None)
    )

    # Xóa member.
    await db.delete(target_member)

    # Commit một lần để tránh cập nhật dở dang.
    await db.commit()

    # Invalidate cache các Project bị ảnh hưởng.
    for project_id in affected_project_ids:
        await invalidate_task_cache(project_id)


@router.patch(
    "/{workspace_id}/members/{user_id}/role",
    response_model=WorkspaceMemberResponse,
    summary="Update a workspace member role",
)
async def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    data: WorkspaceMemberRoleUpdate,
    member: Annotated[WorkspaceMember, Depends(get_workspace_member)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm membership của current_user trong Workspace.
    # Tại sao? Phải xác định người thực hiện hành động
    # có thuộc Workspace này hay không.
    # Nếu không thuộc → HTTP 404.

    # 2. Kiểm tra current_user có role OWNER.
    # Tại sao? Chỉ OWNER được thay đổi quyền thành viên.
    # Nếu là EDITOR hoặc VIEWER → HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.ONLY_OWNER_CAN_UPDATE_MEMBERS)

    # 3. Tìm membership của user_id cần thay đổi.
    # Tại sao? Chúng ta sửa role trên WorkspaceMember,
    # chứ không sửa role toàn hệ thống ở bảng users.
    # Không tìm thấy → HTTP 404.

    target_member = await db.get(
        WorkspaceMember,
        (workspace_id, user_id),
    )
    if target_member is None:
        raise NotFoundException(ErrorMessages.WORKSPACE_MEMBER_NOT_FOUND)

    # 4. Không cho phép thay đổi role của OWNER.
    # Tại sao? OWNER được xác định khi tạo Workspace.
    # Việc chuyển quyền sở hữu phải là một chức năng riêng.
    if target_member.role == WorkspaceRole.OWNER:
        raise ForbiddenException(ErrorMessages.CANNOT_UPDATE_OWNER_ROLE)

    # 5. Không cho phép gán role OWNER.
    # Tại sao? API này chỉ hỗ trợ chuyển đổi
    # giữa EDITOR và VIEWER.

    if data.role == WorkspaceRole.OWNER:
        raise ValidationException(ErrorMessages.CANNOT_ASSIGN_OWNER_ROLE)

    # 6. Cập nhật target_member.role = data.role.
    # SQLAlchemy sẽ theo dõi thay đổi trên ORM object.
    target_member.role = data.role

    # 7. await db.commit().
    # Lưu role mới vào PostgreSQL.
    await db.commit()

    # 8. await db.refresh(target_member).
    # Đồng bộ object trước khi trả response.
    await db.refresh(target_member)

    # 9. return target_member.
    return target_member
