"""Проверяет отметку настоящего места старта: она появляется и не роняет показ."""

from pathlib import Path

from torrcast.adapters.stream_pack.landed_path import landed_path
from torrcast.adapters.stream_pack.mark_landed import mark_landed


def test_the_show_leaves_its_real_starting_place(tmp_path: Path) -> None:
    """Показ сел не там, где закладка звала - и это число доказывает файл, а не память."""
    mark_landed(tmp_path, 2450.0)
    assert landed_path(tmp_path).read_text(encoding="utf-8") == repr(2450.0)


def test_a_directory_that_is_gone_does_not_kill_the_show(tmp_path: Path) -> None:
    """Каталог вычистили окном - показ от этого не падает: отметка не главнее показа."""
    mark_landed(tmp_path / "нет-такого", 10.0)  # без исключения
