from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import Enum as SQLEnum
from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import WorkspaceRole
from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace import Workspace


class WorkspaceMember(Base):
    __tablename__ = "workspace_members"

    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"),
        primary_key=True,
    )

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
        index=True,
    )

    role: Mapped[WorkspaceRole] = mapped_column(
        SQLEnum(WorkspaceRole),
        default=WorkspaceRole.VIEWER,
        nullable=False,
    )

    user: Mapped[User] = relationship(
        "User",
        back_populates="memberships",
    )

    workspace: Mapped[Workspace] = relationship(
        "Workspace",
        back_populates="members",
    )
