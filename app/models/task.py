from datetime import date, datetime
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, String, Text, func
from sqlalchemy import Enum as SQLEnum
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskStatus(str, Enum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    IN_REVIEW = "IN_REVIEW"
    DONE = "DONE"


class TaskPriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    URGENT = "URGENT"


class Task(Base):
    __tablename__ = "tasks"

    id: Mapped[int] = mapped_column(primary_key=True)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id"),
        nullable=False,
        index=True,
    )

    assignee_id: Mapped[int | None] = mapped_column(
        ForeignKey("users.id"),
        nullable=True,
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)

    description: Mapped[str | None] = mapped_column(
        Text,
        nullable=True,
    )

    status: Mapped[TaskStatus] = mapped_column(
        SQLEnum(TaskStatus),
        default=TaskStatus.TODO,
        nullable=False,
    )

    priority: Mapped[TaskPriority] = mapped_column(
        SQLEnum(TaskPriority),
        default=TaskPriority.MEDIUM,
        nullable=False,
    )

    due_date: Mapped[date | None] = mapped_column(
        Date,
        nullable=True,
    )

    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
