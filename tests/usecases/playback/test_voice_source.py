"""Зеркало источника отдельной дорожки: откуда показ берёт звук этой серии."""

from __future__ import annotations

from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.entry import Entry
from torrcast.domain.torr_file import TorrFile
from torrcast.usecases.playback.voice_source import voice_source

_FILES = [
    TorrFile(index=0, name="Erin/Erin - 01.mkv", size=700),
    TorrFile(index=1, name="Erin/Erin - 02.mkv", size=700),
    TorrFile(index=2, name="Erin/Sound/Erin - 01.mka", size=100),
    TorrFile(index=3, name="Erin/Sound/Erin - 02.mka", size=100),
]


def _entry(file_idx: int, apart: bool) -> Entry:
    return Entry(title="Эрин", magnet="magnet:?x", file_idx=file_idx, voiced_apart=apart)


def test_entry_without_the_mark_asks_the_release_nothing() -> None:
    """Звук внутри видео - второго входа нет, и списка файлов никто не спрашивает."""
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert voice_source(engine, "hash", _entry(0, apart=False)) == ""
    assert engine.stream_requests == []


def test_each_episode_gets_the_address_of_its_own_track() -> None:
    """Файл ищется под текущую серию заново: переход на вторую берёт её дорожку."""
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert voice_source(engine, "hash", _entry(1, apart=True)) == "http://fake/hash/3"


def test_a_release_that_lost_the_track_plays_from_the_video() -> None:
    """Правило файла не нашло - показ идёт звуком из видео, а не падает."""
    engine = FakeTorrentEngine(torrent_files=[_FILES[0], _FILES[1]])

    assert voice_source(engine, "hash", _entry(0, apart=True)) == ""


def test_a_file_missing_from_the_release_answers_nothing() -> None:
    """Записанного видеофайла в раздаче нет - искать рядом с ним нечего."""
    engine = FakeTorrentEngine(torrent_files=list(_FILES))

    assert voice_source(engine, "hash", _entry(77, apart=True)) == ""
