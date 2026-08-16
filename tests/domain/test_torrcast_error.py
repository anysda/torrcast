"""Проверки базовой ошибки torrcast."""

from torrcast.domain.torrcast_error import TorrcastError


def test_keeps_message() -> None:
    assert str(TorrcastError("сбой")) == "сбой"
