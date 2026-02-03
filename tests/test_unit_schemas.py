import pytest
from pydantic import ValidationError

from app.schemas import UserUpdate


def test_user_update_invalid_email():
    with pytest.raises(ValidationError):
        UserUpdate(email="bad-email")


def test_user_update_invalid_password():
    with pytest.raises(ValidationError):
        UserUpdate(password="weak")


def test_user_update_invalid_name():
    with pytest.raises(ValidationError):
        UserUpdate(name="@@@")
