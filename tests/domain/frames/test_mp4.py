"""Проверяет доступность чистого разбора MP4."""

from torrcast.domain.frames.mp4 import keys


def test_parser_is_callable() -> None:
    """Точка разбора не зависит от HTTP-адаптера."""
    assert callable(keys)
