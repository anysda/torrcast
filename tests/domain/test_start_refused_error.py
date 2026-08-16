"""Проверки ошибки отказа приёмника."""

from torrcast.domain.infra_error import InfraError
from torrcast.domain.start_refused_error import StartRefusedError


def test_is_infrastructure_error() -> None:
    assert issubclass(StartRefusedError, InfraError)
