"""Зеркало третьей части таблиц разбора имён."""

from torrcast.domain._name_data.data_3 import VIDEO_EXT


def test_video_extensions_table_is_exposed() -> None:
    assert ".mkv" in VIDEO_EXT
