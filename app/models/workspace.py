from __future__ import annotations
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, String, func, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User
    from app.models.workspace_member import WorkspaceMember

class Workspace(Base):
    __tablename__ = "workspaces"

    id: Mapped[int] = mapped_column(primary_key=True)

    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False
    )

    owner_id: Mapped[int] = mapped_column(
        ForeignKey("users.id")
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    owner: Mapped[User] = relationship(
        "User",
        back_populates="owned_workspaces",
        foreign_keys=[owner_id]
    )

    members: Mapped[list[WorkspaceMember]] = relationship(
        "WorkspaceMember",
        back_populates="workspace",
    )