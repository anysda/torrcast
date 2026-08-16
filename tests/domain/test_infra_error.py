"""Проверки иерархии инфраструктурных ошибок."""

from torrcast.domain.infra_error import InfraError
from torrcast.domain.torrcast_error import TorrcastError


def test_is_torrcast_error() -> None:
    assert issubclass(InfraError, TorrcastError)
