from datetime import date, timedelta

import pytest
from pydantic import ValidationError

from app.schemas.task import TaskCreate, TaskUpdate


def test_due_date_omitted():
    data = TaskUpdate(title="Updated task")

    result = data.model_dump(exclude_unset=True)

    assert "due_date" not in result


def test_due_date_can_be_cleared():
    data = TaskUpdate(due_date=None)

    result = data.model_dump(exclude_unset=True)

    assert "due_date" in result
    assert result["due_date"] is None


def test_due_date_can_be_updated():
    expected_date = date.today() + timedelta(days=1)
    data = TaskUpdate(due_date=expected_date)

    result = data.model_dump(exclude_unset=True)

    assert result["due_date"] == expected_date


@pytest.mark.parametrize("schema", [TaskCreate, TaskUpdate])
def test_due_date_in_the_past_is_rejected(schema):
    due_date = date.today() - timedelta(days=1)
    payload = {"due_date": due_date}
    if schema is TaskCreate:
        payload["title"] = "Test task"

    with pytest.raises(ValidationError) as exc:
        schema(**payload)

    assert any(error["loc"] == ("due_date",) for error in exc.value.errors())


@pytest.mark.parametrize("schema", [TaskCreate, TaskUpdate])
def test_due_date_today_is_allowed(schema):
    payload = {"due_date": date.today()}
    if schema is TaskCreate:
        payload["title"] = "Test task"

    assert schema(**payload).due_date == date.today()


def test_invalid_due_date():
    with pytest.raises(ValidationError):
        TaskUpdate(due_date="not-a-date")
