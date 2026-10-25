from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import delete, exists, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.core.redis_cache import (
    invalidate_task_cache,
)
from app.db.session import get_db
from app.models.project import Project
from app.models.task import Task
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_member import WorkspaceMember, WorkspaceRole
from app.schemas.workspace import (
    WorkspaceCreate,
    WorkspaceMemberCreate,
    WorkspaceMemberResponse,
    WorkspaceMemberRoleUpdate,
    WorkspaceResponse,
    WorkspaceUpdate,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post(
    "",
    response_model=WorkspaceResponse,
    status_code=status.HTTP_201_CREATED,
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


@router.get("", response_model=list[WorkspaceResponse])
async def list_workspaces(
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Viết SELECT Workspace JOIN WorkspaceMember.
    # Vì owner_id chỉ cho biết người sở hữu, không cho biết
    # toàn bộ thành viên, nên phải JOIN bảng workspace_members.

    # 2. Dùng WHERE lọc membership của current_user.id.
    # Nếu không lọc, User có thể nhìn thấy Workspace
    # của những người khác.

    query = (
        select(Workspace)
        .join(
            WorkspaceMember,
            Workspace.id == WorkspaceMember.workspace_id,
        )
        .where(WorkspaceMember.user_id == current_user.id)
    )

    # 3. Chạy truy vấn bằng await db.scalars(query).
    # scalars() trả về các Workspace ORM object thay vì
    # các Row chứa Workspace.
    result = await db.scalars(query)
    # 4. Dùng result.all() lấy danh sách Workspace.
    # API trả về list nên không dùng first().
    workspaces = result.all()
    # 5. Return danh sách Workspace.
    return workspaces


@router.get(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
async def get_workspace(
    workspace_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Bước 1: Tìm Workspace theo workspace_id.
    # Cần kiểm tra bản ghi có tồn tại trước khi trả dữ liệu.
    # Nếu không tồn tại, trả HTTP 404.
    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Bước 2: Kiểm tra WorkspaceMember với:
    # workspace_id = workspace_id
    # user_id = current_user.id
    # Vì biết workspace_id chưa có nghĩa user được phép xem nó.

    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )

    # Bước 3: Nếu membership không tồn tại, trả HTTP 404.
    # Tránh để người ngoài phân biệt Workspace có tồn tại hay không.

    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    # Bước 4: Nếu có membership, trả Workspace.
    return workspace


@router.patch(
    "/{workspace_id}",
    response_model=WorkspaceResponse,
)
async def update_workspace(
    workspace_id: int,
    data: WorkspaceUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm Workspace theo ID.
    # Cần xác nhận Workspace tồn tại trước khi cập nhật.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 2. Tìm WorkspaceMember theo (workspace_id, current_user.id).
    # Vì mỗi User có một role riêng trong từng Workspace.
    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )

    # 3. Nếu không phải thành viên, trả HTTP 404.
    # Tránh tiết lộ sự tồn tại của Workspace cho người ngoài.
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 4. Nếu member.role != WorkspaceRole.OWNER, trả HTTP 403.
    # Chỉ OWNER mới được phép đổi tên Workspace.

    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER can update workspace",
        )

    # 5. Gán tên mới từ data.name vào workspace.name.
    # SQLAlchemy theo dõi thay đổi trên ORM object.
    workspace.name = data.name

    # 6. await db.commit().
    # Lưu thay đổi vào PostgreSQL.
    await db.commit()

    # 7. await db.refresh(workspace).
    # Đồng bộ object với dữ liệu đã lưu trong database.
    await db.refresh(workspace)

    # 8. Trả về Workspace.
    return workspace


@router.delete(
    "/{workspace_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_workspace(
    workspace_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm Workspace theo workspace_id.
    # Cần biết Workspace có tồn tại trước khi xử lý xóa.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 2. Kiểm tra membership của current_user.
    # Không phải thành viên thì trả 404 để hạn chế
    # tiết lộ sự tồn tại của Workspace.

    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )
    if member is None:
        raise HTTPException(
            status_code=404,
            detail="Workspace not found",
        )
    # 3. Kiểm tra member.role có phải OWNER không.
    # Chỉ OWNER có quyền xóa toàn bộ Workspace.
    # Nếu không đủ quyền thì trả 403.

    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER can delete workspace",
        )

    # 4. Kiểm tra Workspace còn Project hay không.
    # Nếu còn Project thì trả 409, tránh lỗi Foreign Key.

    has_projects = await db.scalar(
        select(exists().where(Project.workspace_id == workspace_id))
    )

    if has_projects:
        raise HTTPException(
            status_code=409,
            detail="Cannot delete workspace that contains projects",
        )

    # 5. Xóa Workspace bằng await db.delete(workspace).
    # AsyncSession.delete() là coroutine nên phải await.
    try:
        await db.execute(
            delete(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)
        )

        await db.delete(workspace)
        await db.commit()

    except IntegrityError:
        await db.rollback()

        raise HTTPException(
            status_code=409,
            detail="Workspace has related records and cannot be deleted",
        )


@router.post(
    "/{workspace_id}/members",
    status_code=status.HTTP_201_CREATED,
    response_model=WorkspaceMemberResponse,
)
async def add_workspace_member(
    workspace_id: int,
    data: WorkspaceMemberCreate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # Bước 1: Tìm Workspace theo workspace_id.
    # Tại sao? Chúng ta không thể thêm thành viên vào
    # một Workspace không tồn tại. Nếu không tìm thấy → 404.

    workspace = await db.get(Workspace, workspace_id)

    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # Bước 2: Tìm membership của current_user.
    # Tại sao? Đăng nhập thành công không đồng nghĩa
    # với việc có quyền quản lý mọi Workspace.
    # Nếu không thuộc Workspace → 404.

    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )
    # Bước 3: Kiểm tra current_user có role OWNER không.
    # Tại sao? Chỉ OWNER mới được phép quản lý thành viên.
    # EDITOR và VIEWER phải nhận HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER can add workspace members",
        )

    # Bước 4: Kiểm tra data.role không phải OWNER.
    # Tại sao? Không cho phép một người thêm OWNER mới
    # thông qua endpoint này. Nếu vi phạm → 422.

    if data.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Cannot assign OWNER role",
        )

    # Bước 5: Tìm User cần thêm bằng data.user_id.
    # Tại sao? user_id phải tham chiếu đến User tồn tại.
    # Nên kiểm tra is_active để không mời tài khoản bị khóa.
    user = await db.get(User, data.user_id)
    if user is None or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
        )
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
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="User is already a workspace member",
        )

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
    response_model=list[WorkspaceMemberResponse],
)
async def list_workspace_members(
    workspace_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Kiểm tra current_user có membership trong Workspace không.
    # Vì API chỉ dành cho thành viên của Workspace.
    # Nếu không có membership, trả 404 để tránh lộ thông tin.
    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 2. SELECT WorkspaceMember và lọc theo workspace_id.
    # Vì ta muốn lấy TẤT CẢ membership của Workspace,
    # không chỉ membership của current_user.
    query = select(WorkspaceMember).where(WorkspaceMember.workspace_id == workspace_id)

    # 3. Dùng await db.scalars(query).
    # Vì SELECT trả các ORM object WorkspaceMember,
    # không cần lấy các Row chứa nhiều cột riêng biệt.
    result = await db.scalars(query)
    # 4. Dùng result.all() và return.
    # Vì đây là API danh sách, không dùng first().
    return result.all()


@router.delete(
    "/{workspace_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_workspace_member(
    workspace_id: int,
    user_id: int,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Kiểm tra membership của người đang đăng nhập.
    # Vì chỉ người thuộc Workspace mới có thể quản lý thành viên.
    # Nếu không tìm thấy, trả HTTP 404.
    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found",
        )

    # 2. Kiểm tra current_user có role OWNER không.
    # Vì EDITOR và VIEWER không có quyền xóa thành viên.
    # Nếu không phải OWNER, trả HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER can delete members",
        )

    # 3. Tìm WorkspaceMember cần xóa bằng (workspace_id, user_id).
    # Vì phải xác định chính xác người cần xóa trong Workspace này.
    # Nếu không tìm thấy, trả HTTP 404.

    target_member = await db.get(
        WorkspaceMember,
        (workspace_id, user_id),
    )
    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace member not found",
        )

    # 4. Không cho phép xóa OWNER.
    # Vì Workspace phải luôn có một OWNER theo thiết kế hiện tại.
    # Nếu thành viên cần xóa là OWNER, trả HTTP 403.
    if target_member.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không thể delete người có role là OWNER",
        )

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
)
async def update_workspace_member_role(
    workspace_id: int,
    user_id: int,
    data: WorkspaceMemberRoleUpdate,
    current_user: Annotated[User, Depends(get_current_user)],
    db: Annotated[AsyncSession, Depends(get_db)],
):
    # 1. Tìm membership của current_user trong Workspace.
    # Tại sao? Phải xác định người thực hiện hành động
    # có thuộc Workspace này hay không.
    # Nếu không thuộc → HTTP 404.

    member = await db.get(
        WorkspaceMember,
        (workspace_id, current_user.id),
    )
    if member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 2. Kiểm tra current_user có role OWNER.
    # Tại sao? Chỉ OWNER được thay đổi quyền thành viên.
    # Nếu là EDITOR hoặc VIEWER → HTTP 403.

    if member.role != WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only OWNER can update members",
        )

    # 3. Tìm membership của user_id cần thay đổi.
    # Tại sao? Chúng ta sửa role trên WorkspaceMember,
    # chứ không sửa role toàn hệ thống ở bảng users.
    # Không tìm thấy → HTTP 404.

    target_member = await db.get(
        WorkspaceMember,
        (workspace_id, user_id),
    )
    if target_member is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Workspace not found",
        )

    # 4. Không cho phép thay đổi role của OWNER.
    # Tại sao? OWNER được xác định khi tạo Workspace.
    # Việc chuyển quyền sở hữu phải là một chức năng riêng.
    if target_member.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Không cho phép thay đổi role của OWNER",
        )

    # 5. Không cho phép gán role OWNER.
    # Tại sao? API này chỉ hỗ trợ chuyển đổi
    # giữa EDITOR và VIEWER.

    if data.role == WorkspaceRole.OWNER:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Không cho phép thay đổi role thành OWNER",
        )

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
