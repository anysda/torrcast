"""Зеркало честной строки про авто-выбор крупнейшего видеофайла раздачи."""

from __future__ import annotations

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback.pack_note import pack_note


def test_the_pack_line_names_count_largest_and_share() -> None:
    """Видеофайлов несколько - строка называет их счёт и долю крупнейшего.

    Текст в раздаче лежит меж видеофайлами нарочно: считается только видео, той же
    меркой, что и сам выбор.
    """
    files = [
        TorrFile(index=1, name="сборник/часть-01.mkv", size=100),
        TorrFile(index=2, name="сборник/обложка.jpg", size=10),
        TorrFile(index=3, name="сборник/часть-02.mkv", size=900),
    ]
    want = phrase("playback.picking_largest_file", total=2, share="0.90")
    assert pack_note(files) == want


def test_the_pack_line_is_silent_where_there_is_nothing_to_choose() -> None:
    """Один видеофайл - не решение, а единственный вариант: строка была бы шумом."""
    assert pack_note([TorrFile(index=1, name="кино/film.mkv", size=100)]) == ""
    assert pack_note([TorrFile(index=1, name="кино/readme.txt", size=1)]) == ""
