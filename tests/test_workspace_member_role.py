from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.api.v1.workspaces import update_workspace_member_role
from app.core.enums import WorkspaceRole
from app.core.error_messages import ErrorMessages
from app.core.exceptions import ForbiddenException
from app.schemas.workspace import WorkspaceMemberRoleUpdate


@pytest.mark.asyncio
async def test_cannot_change_existing_owner_role():
    current_member = SimpleNamespace(role=WorkspaceRole.OWNER)
    target_member = SimpleNamespace(role=WorkspaceRole.OWNER)
    db = AsyncMock()
    db.get.return_value = target_member

    with pytest.raises(ForbiddenException) as exc:
        await update_workspace_member_role(
            workspace_id=1,
            user_id=2,
            data=WorkspaceMemberRoleUpdate(role=WorkspaceRole.EDITOR),
            member=current_member,
            db=db,
        )

    assert exc.value.status_code == 403
    assert exc.value.message == ErrorMessages.CANNOT_UPDATE_OWNER_ROLE
    db.commit.assert_not_awaited()