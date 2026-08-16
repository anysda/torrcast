"""Проверки ошибки TorrServer."""

from torrcast.domain.infra_error import InfraError
from torrcast.domain.server_down_error import ServerDownError


def test_is_infrastructure_error() -> None:
    assert issubclass(ServerDownError, InfraError)
