"""Проверяет подготовку каталога сегментов: он чистый, и следа прошлого показа в нём нет."""

from pathlib import Path

from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.playing_flag import playing_flag


def test_the_pieces_of_the_previous_show_are_swept_out(tmp_path: Path) -> None:
    """Под теми же именами лежало другое место фильма: остаться им нельзя.

    Это tmpfs, и куска прошлой серии хватит, чтобы новый показ отдал приёмнику чужую
    картинку под верным именем.
    """
    room = tmp_path / "пак"
    room.mkdir()
    (room / "v0.ts").write_bytes(b"old")
    (room / "index.m3u8").write_text("#EXTM3U\n")
    (room / "init.mp4").write_bytes(b"old")
    (room / "init.mp4.part").write_bytes("обрывок".encode())
    keep = room / "заметка.txt"
    keep.write_text("не сегмент")

    assert hls_dir(str(room)) == room
    assert not (room / "v0.ts").exists() and not (room / "index.m3u8").exists()
    assert not (room / "init.mp4").exists() and not (room / "init.mp4.part").exists()
    assert keep.exists(), "чужие файлы каталога не наши, и трогать их незачем"


def test_the_flag_of_the_previous_show_does_not_survive(tmp_path: Path) -> None:
    """Флажок картинки прошлого показа доказывает не то: новый обязан доказать сам."""
    room = tmp_path / "пак"
    room.mkdir()
    mark_playing(room)
    hls_dir(str(room))
    assert not playing_flag(room).exists()


def test_a_directory_that_is_not_there_yet_is_made(tmp_path: Path) -> None:
    assert hls_dir(str(tmp_path / "новый" / "пак")).is_dir()
