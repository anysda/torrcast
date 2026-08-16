"""Проверяет структурную совместимость источника диапазонов."""

from torrcast.domain.frames.range_reader import RangeReader


def test_protocol_is_available() -> None:
    """Контракт импортируется отдельно от транспорта."""
    assert RangeReader.__name__ == "RangeReader"
