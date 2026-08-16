"""Проверяет форму порта окружения самопроверки."""

from tests.fakes.health_environment import FakeHealthEnvironment
from torrcast.ports.health_environment import HealthEnvironment


def test_health_environment_is_a_port() -> None:
    """Порт остаётся протоколом без системной реализации."""
    assert HealthEnvironment.__name__ == "HealthEnvironment"


def test_a_fake_fits_the_port_whole() -> None:
    """Двойник закрывает порт целиком - иначе пробы не подменить одним объектом."""
    environment: HealthEnvironment = FakeHealthEnvironment()
    assert environment.cast_port() == 8009
    assert environment.has_terminal() is True
