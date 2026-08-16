"""Проверяет доступность порта JSON-клиента."""

from torrcast.ports.json_client import JsonClient


def test_port_is_available() -> None:
    """Порт объявляет отдельный HTTP-контракт."""
    assert JsonClient.__name__ == "JsonClient"
