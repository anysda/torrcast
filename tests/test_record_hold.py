"""Записанные раздачи держатся подключёнными, пока страница их называет, и отпускаются после."""

from __future__ import annotations

from collections.abc import Callable

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from torrcast.domain.entry import Entry
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.torrent_claims import CLAIMS
from web.record_hold import BEAT, HOLD_MAX, LEASE, RecordHold


class _Page:
    """Часы, ожидание и очередь потоков держателя в руках теста."""

    def __init__(self, entries: dict[str, Entry], engine: FakeTorrentEngine) -> None:
        self.now = 0.0
        self.spawned: list[Callable[[], None]] = []
        self.holder = RecordHold(
            engines=lambda base_url, timeout: engine,
            entries=lambda: entries,
            clock=lambda: self.now,
            wait=self.wait,
            spawn=self.spawned.append,
        )
        self.on_wait: Callable[[], None] = lambda: None

    def wait(self, seconds: float) -> None:
        self.now += seconds
        self.on_wait()

    def run(self) -> None:
        while self.spawned:
            self.spawned.pop(0)()


def _entry(magnet: str, torrent: str = "") -> Entry:
    return Entry(title="Тачки", magnet=magnet, pos=60.0, dur=6000.0, torrent=torrent)


@pytest.fixture
def state() -> FakeStateStore:
    store = FakeStateStore()
    state_slot.install(store)
    return store


def test_each_recorded_release_on_the_page_is_held_once(state: FakeStateStore) -> None:
    entries = {"a": _entry("magnet:a"), "b": _entry("magnet:a"), "c": _entry("magnet:c")}
    page = _Page(entries, FakeTorrentEngine())

    assert page.holder.touch("http://ts", ["a", "b", "c", "unknown"]) == 2
    assert page.holder.touch("http://ts", ["a", "c"]) == 0
    assert len(page.spawned) == 2
    assert page.holder.held() == {"magnet:a", "magnet:c"}


def test_no_more_than_the_ceiling_is_held_at_once(state: FakeStateStore) -> None:
    entries = {f"k{n}": _entry(f"magnet:{n}") for n in range(HOLD_MAX + 5)}
    page = _Page(entries, FakeTorrentEngine())

    assert page.holder.touch("http://ts", list(entries)) == HOLD_MAX


def test_a_held_release_is_woken_each_step_and_dropped_once_the_page_stops_calling(
    state: FakeStateStore,
) -> None:
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])

    page.run()

    assert engine.added == ["magnet:a"] * int(LEASE / BEAT)
    assert engine.dropped == ["hash"]
    assert page.holder.held() == set()
    assert not CLAIMS.claimed("hash")


def test_a_page_that_keeps_calling_keeps_the_release(state: FakeStateStore) -> None:
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])
    calls = iter(range(5))

    def call_again() -> None:
        if next(calls, None) is not None:
            page.holder.touch("http://ts", ["a"])

    page.on_wait = call_again

    page.run()

    assert len(engine.added) == 5 + int(LEASE / BEAT)
    assert page.spawned == []


def test_a_release_the_show_took_over_is_not_dropped(state: FakeStateStore) -> None:
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])
    page.on_wait = lambda: state.save(WatchState({"a": _entry("magnet:a", "hash")}))

    page.run()

    assert engine.dropped == []
    assert page.holder.held() == set()


def test_a_release_another_holder_in_the_process_claims_is_not_dropped(
    state: FakeStateStore,
) -> None:
    engine = FakeTorrentEngine()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])
    show = _Page({}, engine)  # any live holder in the process
    CLAIMS.claim("hash", show)
    try:
        page.run()
    finally:
        CLAIMS.unclaim("hash", show)

    assert engine.dropped == []


def test_a_silent_service_leaves_nothing_to_drop_and_the_release_can_be_held_again(
    state: FakeStateStore,
) -> None:
    class _Silent(FakeTorrentEngine):
        def add(self, magnet: str) -> str:
            raise TorrcastError("TorrServer не ответил")

    engine = _Silent()
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.touch("http://ts", ["a"])

    page.run()

    assert engine.dropped == []
    assert page.holder.touch("http://ts", ["a"]) == 1
