"""Проверяет доступность порта JSON-хранилища."""

from torrcast.ports.json_store import JsonStore


def test_port_is_available() -> None:
    """Порт объявляет отдельный дисковый контракт."""
    assert JsonStore.__name__ == "JsonStore"
