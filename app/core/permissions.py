from collections.abc import Collection

from app.core.enums import ProjectStatus, WorkspaceRole
from app.core.error_messages import ErrorMessages
from app.core.exceptions import ConflictException, ForbiddenException
from app.models.project import Project


def require_workspace_role(
    role: WorkspaceRole,
    allowed_roles: Collection[WorkspaceRole],
) -> None:
    if role not in allowed_roles:
        raise ForbiddenException(ErrorMessages.FORBIDDEN)


def require_write_access(role: WorkspaceRole) -> None:
    require_workspace_role(
        role,
        (WorkspaceRole.OWNER, WorkspaceRole.EDITOR),
    )


def require_active_project(project: Project) -> None:
    # Project đã archive không được chỉnh sửa.
    if project.status == ProjectStatus.ARCHIVED:
        raise ConflictException(ErrorMessages.PROJECT_ARCHIVED)
