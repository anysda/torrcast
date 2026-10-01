"""Держатель паркует только первые записи ряда и греет их, кто бы из страниц ни звал."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.test_record_hold import _live, _Page, state
from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.entry import Entry
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.torrent_hash import _torrent_hash
from torrcast.usecases.torrent_claims import CLAIMS
from web.record_sweep import record_sweep
from web.record_warm import RecordWarm
from web.warm_job import WarmJob

__all__ = ["state"]

URL = "http://ts"


def _record(n: int, updated: int) -> Entry:
    return Entry(
        title=f"Фильм {n}",
        magnet=f"magnet:?xt=urn:btih:{n:040x}",
        pos=60.0,
        dur=6000.0,
        updated=f"2026-01-01T00:{updated // 60:02d}:{updated % 60:02d}",
    )


def _row(count: int) -> dict[str, Entry]:
    """Записи ``k0``..: ``k0`` свежая."""
    return {f"k{n}": _record(n, count - n) for n in range(count)}


@dataclass
class _Base(FakeTorrentEngine):
    """База службы: ``park`` закрывает раздачу и оставляет её в базе с кэшем, ``drop`` сносит."""

    db: set[str] = field(default_factory=set)
    parked: list[str] = field(default_factory=list)

    def add(self, magnet: str) -> str:
        self.db.add(_torrent_hash(magnet))
        return _torrent_hash(magnet)

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return [TorrFile(0, "Cars.mkv")]

    def park(self, torrent_hash: str) -> bool:
        self.parked.append(torrent_hash)
        return True

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        self.db.discard(torrent_hash)
        return True

    def hashes(self) -> set[str]:
        return set(self.db)


@pytest.mark.parametrize(("key", "parked"), [("k0", True), (f"k{WARM_ROW}", False)])
def test_only_a_first_record_of_the_row_is_parked(
    state: FakeStateStore, key: str, parked: bool
) -> None:
    base = _Base()
    page = _Page(_row(WARM_ROW + 1), base)
    page.holder.touch(URL, [key])

    page.run()

    assert (bool(base.parked), bool(base.dropped)) == (parked, not parked)


def test_twenty_home_openings_leave_no_more_than_the_first_records_in_the_service(
    state: FakeStateStore,
) -> None:
    """Прогретые записи, выпавшие из ряда, лежали в базе службы с кэшем 40-200 МБ навсегда."""
    entries = _row(5)
    base = _Base()
    page = _Page(entries, base)

    def sweep_now(url: str, row: tuple[str, ...]) -> None:
        record_sweep(base, entries, CLAIMS.claimed)

    page.holder.sweep = sweep_now
    for opening in range(20):
        entries[f"n{opening}"] = _record(100 + opening, 1000 + opening)  # показ сменил ряд
        row = sorted(entries, key=lambda k: entries[k].updated, reverse=True)[:WARM_ROW]
        page.holder.touch(URL, row)  # главная зовёт первые записи (web/history.py)
        page.run()
        page.holder.touch(URL, [f"k{opening % 5}"])  # карточка старой записи с главной
        page.run()

    assert len(base.db) <= WARM_ROW, f"в базе службы {len(base.db)} раздач истории"


def test_every_touch_hands_the_first_records_of_the_row_to_the_sweep(
    state: FakeStateStore,
) -> None:
    """Сверку зовут с рядом: убран ли он, решает она сама (:class:`web.sweep_later.SweepLater`)."""
    entries = _row(WARM_ROW + 1)
    page = _Page(entries, _live())
    page.holder.touch(URL, [f"k{WARM_ROW}"])  # карточка вне ряда ряд не меняет

    entries["new"] = _record(99, 999)
    page.holder.touch(URL, ["k0"])

    first = tuple(f"k{n}" for n in range(WARM_ROW))
    assert page.swept == [(URL, first), (URL, ("new", *first[:-1]))]


def test_a_card_or_a_second_tab_adds_a_hold_but_not_a_warm_target(state: FakeStateStore) -> None:
    page = _Page(_row(WARM_ROW + 2), _live())
    page.holder.touch(URL, ["k0", "k1", "k2"])

    page.holder.touch(URL, [f"k{WARM_ROW + 1}"])

    wanted = [page.holder.warmer.wants(_record(n, 0).magnet) for n in range(WARM_ROW + 2)]
    assert wanted == [True] * WARM_ROW + [False, False]
    assert _record(WARM_ROW + 1, 0).magnet in page.holder.held()


def test_a_card_and_frequent_history_requests_do_not_cut_a_running_warm(
    state: FakeStateStore,
) -> None:
    """Переспрос истории страницей и карточка обрывали прогрев и начинали его заново."""
    warming: list[Any] = []
    alive_after: list[bool] = []

    def warm(source: str, *, at: float, alive: Any, name: str, done: Any) -> None:
        page.holder.touch(URL, [f"k{WARM_ROW + 1}"])  # карточка над главной
        alive_after.append(alive())
        for order in (["k0", "k1", "k2"], ["k2", "k0"], ["k1"]) * 4:  # переспрос истории
            page.holder.touch(URL, order)
            alive_after.append(alive())
        done.set()

    page = _Page(_row(WARM_ROW + 2), _live(), RecordWarm(warm, lambda: False, spawn=warming.append))
    page.holder.touch(URL, ["k0"])
    page.holder.warmer.offer(WarmJob(_record(0, 0).magnet, "http://fake/0", 60.0, "Cars.mkv"))
    while warming:
        warming.pop(0)()

    assert alive_after == [True] * 13


def test_a_file_without_a_name_is_not_offered_for_warming(state: FakeStateStore) -> None:
    page = _Page({"a": _record(0, 0)}, FakeTorrentEngine(torrent_files=[TorrFile(0, "")]))
    page.holder.touch(URL, ["a"])

    def warm_now() -> None:
        while page.warming:
            page.warming.pop(0)()

    page.on_wait = warm_now
    page.run()

    assert page.warmed == []
