"""Проверяет подключение среды прогрева."""

from torrcast.usecases import warm


def test_warm_accepts_environment() -> None:
    assert warm.warm_root("/tmp/warm").name == "warm"
