"""Проверяет переходный порт пространства совместимости."""

from torrcast.ports.module import module


def test_module_resolves_standard_dependency() -> None:
    assert module("time").monotonic is not None
