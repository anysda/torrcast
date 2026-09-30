"""Отпущенная раздача первой записи ряда паркуется с кэшем, прочая сносится."""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.torrcast_error import TorrcastError
from web.record_release import record_release


@dataclass
class _Parking(FakeTorrentEngine):
    parked: list[str] = field(default_factory=list)

    def park(self, torrent_hash: str) -> bool:
        self.parked.append(torrent_hash)
        return True


@pytest.mark.parametrize(("keep", "parked", "dropped"), [(True, ["h"], []), (False, [], ["h"])])
def test_only_a_record_kept_for_the_click_is_parked(
    keep: bool, parked: list[str], dropped: list[str]
) -> None:
    engine = _Parking()

    record_release(engine, "h", keep=keep)

    assert (engine.parked, engine.dropped) == (parked, dropped)


def test_a_service_that_cannot_park_removes_even_a_first_record() -> None:
    engine = FakeTorrentEngine()

    record_release(engine, "h", keep=True)

    assert engine.dropped == ["h"]


def test_a_silent_service_does_not_break_the_holder() -> None:
    class _Silent(FakeTorrentEngine):
        def drop(self, torrent_hash: str) -> bool:
            raise TorrcastError("TorrServer не ответил")

    record_release(_Silent(), "h", keep=False)
