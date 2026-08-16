"""Проверяет доступность чистого разбора Matroska."""

from torrcast.domain.frames.mkv import keys


def test_parser_is_callable() -> None:
    """Точка разбора не зависит от HTTP-адаптера."""
    assert callable(keys)
