"""Карточка сериала закрывает раздачу первой записи «Продолжить», не стирая прогретого."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.fakes.torrent_engines import FakeTorrentEngines
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from web.episode_lookup import EpisodeLookup
from web.record_hold import RECORD_HOLD

_RELEASE = Release(raw_name="Show s01 WEB-DL 1080p LostFilm", title="Show", magnet="magnet:show")
_FILES = [TorrFile(0, "Show/Show.s01e01.mkv", 700_000_000)]


@dataclass
class _Parking(FakeTorrentEngine):
    parked: list[str] = field(default_factory=list)

    def park(self, torrent_hash: str) -> bool:
        self.parked.append(torrent_hash)
        return True


def _sync(job: Callable[[], None]) -> None:
    job()


def _read(keeps: Callable[[str], bool]) -> _Parking:
    engine = _Parking(torrent_hash="hash-magnet:show", torrent_files=_FILES)
    lookup = EpisodeLookup(engines=FakeTorrentEngines(engine), spawn=_sync, keeps=keeps)
    assert lookup.table(_RELEASE, "http://torrserver") is not None
    return engine


def test_a_first_continue_record_is_parked_not_removed() -> None:
    """Карточка «Рика» меж прогревом и клику стирала кэш, и клик снова ждал рой."""
    engine = _read(lambda magnet: magnet == "magnet:show")

    assert engine.parked == ["hash-magnet:show"]
    assert engine.dropped == []


def test_any_other_release_is_still_removed() -> None:
    engine = _read(lambda magnet: False)

    assert engine.parked == []
    assert engine.dropped == ["hash-magnet:show"], "чужая раздача не копится в службе"


def test_the_card_asks_the_row_the_page_warms() -> None:
    RECORD_HOLD.warmer.name(["magnet:show"])
    try:
        assert EpisodeLookup(engines=FakeTorrentEngines(_Parking())).keeps("magnet:show")
    finally:
        RECORD_HOLD.warmer.name([])
    assert not EpisodeLookup(engines=FakeTorrentEngines(_Parking())).keeps("magnet:show")
