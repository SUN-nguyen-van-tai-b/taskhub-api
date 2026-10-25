from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.models.project import ProjectStatus
from app.models.workspace_member import WorkspaceRole
from app.schemas.task import TaskUpdate
from app.services.task_service import (
    delete_task_service,
    require_active_project,
    require_task_write_access,
    update_task_service,
)


@pytest.mark.parametrize(
    "role",
    [WorkspaceRole.OWNER, WorkspaceRole.EDITOR],
)
def test_owner_editor_can_write(role):
    # Không raise exception nghĩa là có quyền.
    require_task_write_access(role)


def test_viewer_cannot_write():
    with pytest.raises(HTTPException) as exc:
        require_task_write_access(WorkspaceRole.VIEWER)

    assert exc.value.status_code == 403


# ==================================================
# TEST 2: PROJECT ARCHIVED
# ==================================================


def test_archived_project_cannot_be_modified():
    project = SimpleNamespace(status=ProjectStatus.ARCHIVED)

    with pytest.raises(HTTPException) as exc:
        require_active_project(project)

    assert exc.value.status_code == 409


def test_active_project_can_be_modified():
    project = SimpleNamespace(status=ProjectStatus.ACTIVE)

    require_active_project(project)


@pytest.mark.asyncio
async def test_update_task_invalidates_cache():
    task = SimpleNamespace(
        id=10,
        project_id=1,
        title="Old title",
    )

    access = SimpleNamespace(
        task=task,
        project=SimpleNamespace(
            id=1,
            workspace_id=1,
            status=ProjectStatus.ACTIVE,
        ),
        member=SimpleNamespace(role=WorkspaceRole.EDITOR),
    )

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

        # PostgreSQL phải commit.
        db.commit.assert_awaited_once()

        # Redis phải invalidate đúng Project.
        mock_invalidate.assert_awaited_once_with(1)


@pytest.mark.asyncio
async def test_delete_task_invalidates_cache():
    task = SimpleNamespace(id=10, project_id=1)

    access = SimpleNamespace(
        task=task,
        project=SimpleNamespace(
            status=ProjectStatus.ACTIVE,
        ),
        member=SimpleNamespace(role=WorkspaceRole.OWNER),
    )

    db = AsyncMock()

    with patch(
        "app.services.task_service.invalidate_task_cache",
        new_callable=AsyncMock,
    ) as mock_invalidate:
        await delete_task_service(db=db, access=access)

        db.delete.assert_awaited_once_with(task)
        db.commit.assert_awaited_once()
        mock_invalidate.assert_awaited_once_with(1)
