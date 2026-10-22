from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TaskLabel(Base):
    __tablename__ = "task_labels"

    task_id: Mapped[int] = mapped_column(
        ForeignKey("tasks.id", ondelete="CASCADE"),
        primary_key=True,
    )

    label_id: Mapped[int] = mapped_column(
        ForeignKey("labels.id", ondelete="CASCADE"),
        primary_key=True,
    )
