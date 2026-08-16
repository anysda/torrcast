"""Проверки файла раздачи."""

from torrcast.domain.torr_file import TorrFile


def test_base_accepts_windows_separator() -> None:
    assert TorrFile(1, r"season\movie.mkv").base == "movie.mkv"
