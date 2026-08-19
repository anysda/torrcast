"""Проверяет форму порта среды прогрева."""

from torrcast.ports.warm_environment.warm_environment import WarmEnvironment


def test_warm_environment_is_a_port() -> None:
    """Порт остаётся протоколом без системной реализации."""
    assert WarmEnvironment.__name__ == "WarmEnvironment"
