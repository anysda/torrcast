"""Проверяет отметку «картинка на экране»: она появляется и не роняет показ."""

from pathlib import Path

from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag


def test_the_show_that_saw_a_picture_leaves_a_mark(tmp_path: Path) -> None:
    """С этой секунды на экране есть изображение, и доказывает это файл, а не память."""
    mark_playing(tmp_path)
    assert playing_flag(tmp_path).exists()


def test_a_directory_that_is_gone_does_not_kill_the_show(tmp_path: Path) -> None:
    """Каталог вычистили окном - показ от этого не падает: отметка не главнее картинки."""
    mark_playing(tmp_path / "нет-такого")  # без исключения
