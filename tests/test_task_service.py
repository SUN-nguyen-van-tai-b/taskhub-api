from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from app.core.enums import WorkspaceRole
from app.core.error_messages import ErrorMessages
from app.core.exceptions import ConflictException, ForbiddenException
from app.core.permissions import require_active_project, require_write_access
from app.models.project import ProjectStatus
from app.schemas.task import TaskCreate, TaskUpdate
from app.services.task_service import (
    create_task_service,
    delete_task_service,
    update_task_service,
)


def make_access(
    role=WorkspaceRole.OWNER,
    project_status=ProjectStatus.ACTIVE,
):
    task = SimpleNamespace(
        id=10,
        project_id=1,
        title="Old title",
    )

    project = SimpleNamespace(
        id=1,
        workspace_id=1,
        status=project_status,
    )

    member = SimpleNamespace(
        user_id=1,
        role=role,
    )

    return SimpleNamespace(
        task=task,
        project=project,
        member=member,
    )


def assert_http_error(exc_info, expected_status):
    assert exc_info.value.status_code == expected_status


@pytest.mark.parametrize(
    "role",
    [WorkspaceRole.OWNER, WorkspaceRole.EDITOR],
)
def test_owner_editor_can_write(role):
    require_write_access(role)


def test_viewer_cannot_write():
    with pytest.raises(ForbiddenException) as exc:
        require_write_access(WorkspaceRole.VIEWER)

    assert_http_error(exc, 403)


@pytest.mark.asyncio
async def test_viewer_cannot_update_task():
    access = make_access(role=WorkspaceRole.VIEWER)
    db = AsyncMock()

    with pytest.raises(ForbiddenException) as exc:
        await update_task_service(
            db=db,
            data=TaskUpdate(title="Updated title"),
            access=access,
        )

    assert_http_error(exc, 403)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_viewer_cannot_delete_task():
    access = make_access(role=WorkspaceRole.VIEWER)
    db = AsyncMock()

    with pytest.raises(ForbiddenException) as exc:
        await delete_task_service(
            db=db,
            access=access,
        )

    assert_http_error(exc, 403)
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


def test_archived_project_cannot_be_modified():
    project = SimpleNamespace(
        status=ProjectStatus.ARCHIVED,
    )

    with pytest.raises(ConflictException) as exc:
        require_active_project(project)

    assert_http_error(exc, 409)
    assert exc.value.message == ErrorMessages.PROJECT_ARCHIVED


def test_active_project_can_be_modified():
    project = SimpleNamespace(
        status=ProjectStatus.ACTIVE,
    )

    require_active_project(project)


@pytest.mark.asyncio
async def test_archived_project_cannot_update_task():
    access = make_access(
        project_status=ProjectStatus.ARCHIVED,
    )

    db = AsyncMock()

    with pytest.raises(ConflictException) as exc:
        await update_task_service(
            db=db,
            data=TaskUpdate(title="Updated title"),
            access=access,
        )

    assert_http_error(exc, 409)
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_archived_project_cannot_delete_task():
    access = make_access(
        project_status=ProjectStatus.ARCHIVED,
    )

    db = AsyncMock()

    with pytest.raises(ConflictException) as exc:
        await delete_task_service(
            db=db,
            access=access,
        )

    assert_http_error(exc, 409)
    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()


@pytest.mark.asyncio
async def test_create_task_invalidates_cache():
    access = make_access(role=WorkspaceRole.EDITOR)
    db = AsyncMock()

    data = TaskCreate(
        title="New task",
        description="Test task",
    )

    with (
        patch(
            "app.services.task_service.validate_assignee",
            new_callable=AsyncMock,
        ),
        patch(
            "app.services.task_service.invalidate_task_cache",
            new_callable=AsyncMock,
        ) as mock_invalidate,
    ):
        task = await create_task_service(
            db=db,
            data=data,
            access=access,
        )

    assert task.title == "New task"
    assert task.project_id == 1

    db.add.assert_called_once()
    db.commit.assert_awaited_once()
    mock_invalidate.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_update_task_invalidates_cache():
    access = make_access(role=WorkspaceRole.EDITOR)
    db = AsyncMock()

    with patch(
        "app.services.task_service.invalidate_task_cache",
        new_callable=AsyncMock,
    ) as mock_invalidate:
        result = await update_task_service(
            db=db,
            data=TaskUpdate(title="New title"),
            access=access,
        )

    assert result.title == "New title"

    db.commit.assert_awaited_once()
    mock_invalidate.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_delete_task_invalidates_cache():
    access = make_access(role=WorkspaceRole.OWNER)
    db = AsyncMock()

    with patch(
        "app.services.task_service.invalidate_task_cache",
        new_callable=AsyncMock,
    ) as mock_invalidate:
        await delete_task_service(
            db=db,
            access=access,
        )

    db.delete.assert_awaited_once_with(access.task)
    db.commit.assert_awaited_once()
    mock_invalidate.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_viewer_update_does_not_invalidate_cache():
    access = make_access(role=WorkspaceRole.VIEWER)
    db = AsyncMock()

    with (
        patch(
            "app.services.task_service.invalidate_task_cache",
            new_callable=AsyncMock,
        ) as mock_invalidate,
        pytest.raises(ForbiddenException) as exc,
    ):
        await update_task_service(
            db=db,
            data=TaskUpdate(title="New title"),
            access=access,
        )

    assert exc.value.status_code == 403
    db.commit.assert_not_awaited()
    mock_invalidate.assert_not_awaited()


@pytest.mark.asyncio
async def test_archived_delete_does_not_invalidate_cache():
    access = make_access(
        project_status=ProjectStatus.ARCHIVED,
    )
    db = AsyncMock()

    with (
        patch(
            "app.services.task_service.invalidate_task_cache",
            new_callable=AsyncMock,
        ) as mock_invalidate,
        pytest.raises(ConflictException) as exc,
    ):
        await delete_task_service(
            db=db,
            access=access,
        )

    assert exc.value.status_code == 409

    db.delete.assert_not_awaited()
    db.commit.assert_not_awaited()
    mock_invalidate.assert_not_awaited()
