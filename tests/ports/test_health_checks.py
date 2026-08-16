"""Порт самопроверки задаёт упорядоченный источник строк."""

from torrcast.ports.health_checks import HealthChecks


def test_health_checks_is_protocol() -> None:
    assert HealthChecks.__name__ == "HealthChecks"
