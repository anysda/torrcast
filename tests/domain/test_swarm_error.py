"""Проверки ошибки роя."""

from torrcast.domain.infra_error import InfraError
from torrcast.domain.swarm_error import SwarmError


def test_is_infrastructure_error() -> None:
    assert issubclass(SwarmError, InfraError)
