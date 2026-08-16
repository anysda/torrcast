"""Проверяет экспорт порта диапазонного чтения."""

from torrcast.ports.range_reader import RangeReader


def test_port_is_available() -> None:
    """Порт ссылается на транспортно-независимый контракт."""
    assert RangeReader.__name__ == "RangeReader"
