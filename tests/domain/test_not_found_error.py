"""Проверки ошибки пустого результата."""

from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.torrcast_error import TorrcastError


def test_is_torrcast_error() -> None:
    assert issubclass(NotFoundError, TorrcastError)
