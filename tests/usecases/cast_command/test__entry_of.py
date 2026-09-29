"""Запись показа по выбранной раздаче: одна и та же у клика и у головы с карточки."""

from __future__ import annotations

from tests.usecases.cast_command.world import GB, release
from torrcast.cli.parse_args import parse_args
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.media import Media
from torrcast.domain.picture import Picture
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._entry_of import _entry_of
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select.plan import Plan


def _film() -> tuple[Plan, _Prep]:
    pack = release("Кино / Movie BDRip 1080p")
    one = Plan(
        picture=Picture(title="Кино", year=1999, releases=[pack]),
        ranked=[pack],
        runtime=5400.0,
        warn_mbit=16.0,
    )
    prep = _Prep(number=1, release=pack, torrent_hash="h")
    prep.video = TorrFile(index=2, name="кино.mkv", size=8 * GB)
    prep.files = [prep.video]
    prep.media = Media(
        duration=5400.0,
        tracks=(AudioTrack(index=0, language="rus", title="Дубляж"),),
        video="h264",
        height=1080,
        video_bps=8.0 * 1e6,
    )
    return one, prep


def test_the_entry_carries_the_release_the_file_and_the_track() -> None:
    one, prep = _film()

    entry, audio = _entry_of(WatchState(), None, one, prep, parse_args(["кино"]))

    assert entry.audio == audio == 0
    assert entry.magnet == prep.release.magnet and entry.file_idx == 2
    assert entry.pos == 0.0


def test_the_same_pick_gives_the_same_entry() -> None:
    """Голова с карточки и клик строят запись заново: ключ полки обязан совпасть."""
    one, prep = _film()
    args = parse_args(["кино"])

    first, _audio = _entry_of(WatchState(), None, one, prep, args)
    again, _audio = _entry_of(WatchState(), None, one, prep, args)

    assert first == again
