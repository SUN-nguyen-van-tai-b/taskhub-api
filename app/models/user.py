from __future__ import annotations
from datetime import datetime
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum as SQLEnum, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.workspace import Workspace
    from app.models.workspace_member import WorkspaceMember


class UserRole(str, Enum):
    ADMIN = "ADMIN"
    MEMBER = "MEMBER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)

    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        nullable=False,
        index=True,
    )

    full_name: Mapped[str] = mapped_column(String(100))

    hashed_password: Mapped[str] = mapped_column(String(255))

    role: Mapped[UserRole] = mapped_column(
        SQLEnum(UserRole),
        default=UserRole.MEMBER,
        nullable=False,
    )

    is_active: Mapped[bool] = mapped_column(default=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
    )

    owned_workspaces: Mapped[list[Workspace]] = relationship(
        "Workspace",
        back_populates="owner",
        foreign_keys="Workspace.owner_id",
    )

    memberships: Mapped[list[WorkspaceMember]] = relationship(
    "WorkspaceMember",
    back_populates="user",
)