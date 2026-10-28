from datetime import date, datetime
from typing import Annotated

from pydantic import AfterValidator, BaseModel, ConfigDict, Field

from app.core.error_messages import ErrorMessages
from app.models.task import TaskPriority, TaskStatus
from app.schemas.base import BaseSchema, PageSchema


def _validate_due_date(value: date | None) -> date | None:
    if value is not None and value < date.today():
        raise ValueError(ErrorMessages.DUE_DATE_CANNOT_BE_IN_PAST)
    return value


DueDate = Annotated[date | None, AfterValidator(_validate_due_date)]


class TaskCreate(BaseSchema):
    title: str = Field(min_length=2, max_length=200)
    description: str | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    priority: TaskPriority = TaskPriority.MEDIUM
    due_date: DueDate = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    project_id: int
    assignee_id: int | None
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    due_date: date | None
    created_by: int
    created_at: datetime


class TaskUpdate(BaseSchema):
    title: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = None
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = Field(default=None, gt=0)
    due_date: DueDate = None


class TaskPage(PageSchema[TaskResponse]):
    pass


class TaskFilters(BaseModel):
    status: TaskStatus | None = None
    priority: TaskPriority | None = None
    assignee_id: int | None = None
