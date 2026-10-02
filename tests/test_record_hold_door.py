"""Каждый вызов держателя записей к TorrServer идёт за его дверью (:mod:`web.record_door`).

Дверь стоит в четырёх местах держателя: завод раздачи, предложение прогреву, продление и
снос. Тест на каждое своё: вызов, сделанный мимо двери, снова кладёт пачку в общий замок
службы, и клик ждёт её хвост.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.fakes.torrent_engine import FakeTorrentEngine
from tests.test_record_hold import _entry, _Page
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.state_store import slot as state_slot
from web.record_door import RecordDoor


@dataclass
class _Watched(FakeTorrentEngine):
    """Служба, которая помнит, был ли держатель за дверью при каждом вызове."""

    door: RecordDoor = field(default_factory=RecordDoor)
    calls: list[tuple[str, bool]] = field(default_factory=list)

    def _note(self, name: str) -> None:
        self.calls.append((name, self.door._lock.locked()))

    def add(self, magnet: str) -> str:
        self._note("add")
        return super().add(magnet)

    def files(self, torrent_hash: str) -> list[TorrFile]:
        self._note("files")
        return super().files(torrent_hash)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        self._note("stream_url")
        return super().stream_url(torrent_hash, index)

    def drop(self, torrent_hash: str) -> bool:
        self._note("drop")
        return super().drop(torrent_hash)


@pytest.fixture
def calls() -> list[tuple[str, bool]]:
    """Вызовы службы за весь срок аренды одной записи: завод, прогрев, продления, снос."""
    state_slot.install(FakeStateStore())
    engine = _Watched(torrent_files=[TorrFile(0, "Cars.mkv")])
    page = _Page({"a": _entry("magnet:a")}, engine)
    page.holder.door = engine.door
    page.holder.touch("http://ts", ["a"])
    page.run()
    return engine.calls


def _named(calls: list[tuple[str, bool]], name: str) -> list[bool]:
    return [inside for called, inside in calls if called == name]


def test_renewing_a_held_release_goes_through_the_door(calls: list[tuple[str, bool]]) -> None:
    """``_renew`` - основной путь держателя: ``add`` раз в шаг всю аренду."""
    renewals = _named(calls, "add")[1:]
    assert renewals, "держатель ни разу не продлил раздачу"
    assert all(renewals), f"продление мимо двери: {renewals}"


def test_waking_a_release_goes_through_the_door(calls: list[tuple[str, bool]]) -> None:
    assert _named(calls, "add")[:1] == [True], "завод раздачи мимо двери"


def test_offering_the_record_to_warm_goes_through_the_door(calls: list[tuple[str, bool]]) -> None:
    offers = _named(calls, "stream_url")
    assert offers, "запись так и не предложена прогреву"
    assert all(offers), f"предложение прогреву мимо двери: {offers}"


def test_releasing_a_record_goes_through_the_door(calls: list[tuple[str, bool]]) -> None:
    assert _named(calls, "drop") == [True], "снос раздачи мимо двери"
