"""Проверяет доступность порта построчного текстового источника."""

from torrcast.ports.text_source import TextSource


def test_port_is_available() -> None:
    """Порт объявляет отдельный контракт чтения строк."""
    assert TextSource.__name__ == "TextSource"
