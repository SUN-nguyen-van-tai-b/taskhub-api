from datetime import date

import pytest
from pydantic import ValidationError

from app.schemas.task import TaskUpdate


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
    data = TaskUpdate(due_date="2026-11-15")

    result = data.model_dump(exclude_unset=True)

    assert result["due_date"] == date(2026, 11, 15)


def test_invalid_due_date():
    with pytest.raises(ValidationError):
        TaskUpdate(due_date="not-a-date")
