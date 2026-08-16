"""Проверяет системную среду прогрева."""

from torrcast.adapters.warm_environment import environment


def test_warm_environment_has_monotonic_clock() -> None:
    """Монотонные часы доступны через адаптер."""
    assert environment.monotonic() >= 0
