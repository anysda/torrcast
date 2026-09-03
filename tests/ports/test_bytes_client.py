"""Проверяет доступность порта загрузчика байтов."""

from torrcast.ports.bytes_client import BytesClient


def test_port_is_available() -> None:
    """Порт объявляет отдельный договор: ответ - файл, а не дерево значений."""
    assert BytesClient.__name__ == "BytesClient"
