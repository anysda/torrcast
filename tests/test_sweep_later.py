"""Сверка базы службы с рядом идёт фоном, по одной, уступает показу и не теряется."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

import pytest

import web.sweep_later as module
from tests.fakes.state_store import FakeStateStore
from tests.test_record_sweep import _Base, _entries, _hash
from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.torrent_claims import CLAIMS
from web.sweep_later import SweepLater

URL, ROW = "http://ts", ("k0", "k1", "k2")


class _Journal:
    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def mark(self, what: str, **facts: Any) -> None:
        self.marks.append((what, facts))


class _Owner:
    """Держатель раздачи в процессе: карточка, отбор или держатель записей."""


@pytest.fixture
def base(monkeypatch: pytest.MonkeyPatch) -> _Base:
    """Записи ``k0``..``k4`` и все их раздачи в базе службы; за рядом лежат ``k3`` и ``k4``."""
    store = FakeStateStore()
    store.save(WatchState(_entries(WARM_ROW + 2)))
    state_slot.install(store)
    found = _Base({_hash(n) for n in range(WARM_ROW + 2)})
    monkeypatch.setattr(module, "TorrServer", lambda url, timeout: found)
    monkeypatch.setattr(module, "_showing", lambda: False)
    monkeypatch.setattr(module, "journal", _Journal)
    return found


def _inline() -> tuple[SweepLater, list[Callable[[], None]]]:
    """Сверка, чьи потоки копятся списком и идут, когда их запустит тест."""
    started: list[Callable[[], None]] = []
    return SweepLater(spawn=started.append), started


def test_the_sweep_runs_in_its_own_thread_and_is_journaled(
    base: _Base, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _Journal()
    monkeypatch.setattr(module, "journal", lambda: journal)
    started: list[threading.Thread] = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))

    SweepLater()(URL, ROW)
    started[0].run()

    assert started[0].daemon
    assert sorted(base.dropped) == [_hash(WARM_ROW), _hash(WARM_ROW + 1)]
    assert journal.marks == [("уборка записей", {"снесено": 2})]


def test_a_release_held_by_a_claim_or_by_the_show_is_spared(base: _Base) -> None:
    """🔴 Раздачу держит карточка (отметка процесса) или показ (отметка в состоянии).

    Снос выдернул бы источник из-под экрана или дорожки из-под карточки. Проверка идёт
    настоящими отметками: подставная «никто не держит» эту ошибку прятала.
    """
    card, entries = _Owner(), _entries(WARM_ROW + 2)
    entries[f"k{WARM_ROW + 1}"].torrent = _hash(WARM_ROW + 1)  # её играет показ
    state_slot.store().save(WatchState(entries))
    CLAIMS.claim(_hash(WARM_ROW), card)
    try:
        assert module._sweep_records(URL) is True
    finally:
        CLAIMS.unclaim(_hash(WARM_ROW), card)

    assert base.dropped == []
    assert base.listed == {_hash(n) for n in range(WARM_ROW + 2)}


def test_a_live_show_leaves_the_service_alone(base: _Base, monkeypatch: pytest.MonkeyPatch) -> None:
    """Список и снос шли бы по той же службе, что отдаёт кадры показу."""
    monkeypatch.setattr(module, "_showing", lambda: True)

    assert module._sweep_records(URL) is False
    assert base.dropped == []


def test_a_silent_service_is_left_for_the_next_touch(
    base: _Base, monkeypatch: pytest.MonkeyPatch
) -> None:
    def silent() -> set[str]:
        raise TorrcastError("TorrServer не ответил")

    monkeypatch.setattr(base, "hashes", silent)

    assert module._sweep_records(URL) is False
    assert base.dropped == []


@pytest.mark.parametrize("skip", ["show", "silent"])
def test_a_skipped_sweep_runs_again_on_the_next_touch_of_the_same_row(
    base: _Base, monkeypatch: pytest.MonkeyPatch, skip: str
) -> None:
    """🔴 Ряд отмечался убранным до сверки, и уступившая показу сверка терялась до сдвига ряда."""
    listed = base.hashes

    def silent() -> set[str]:
        raise TorrcastError("TorrServer не ответил")

    monkeypatch.setattr(module, "_showing", lambda: skip == "show")
    monkeypatch.setattr(base, "hashes", silent if skip == "silent" else listed)
    sweep, started = _inline()
    sweep(URL, ROW)
    started.pop()()
    assert base.dropped == []

    monkeypatch.setattr(module, "_showing", lambda: False)
    monkeypatch.setattr(base, "hashes", listed)
    sweep(URL, ROW)
    started.pop()()

    assert sorted(base.dropped) == [_hash(WARM_ROW), _hash(WARM_ROW + 1)]


def test_a_swept_row_is_not_swept_again_until_it_moves(base: _Base) -> None:
    sweep, started = _inline()
    sweep(URL, ROW)
    started.pop()()

    for _ in range(5):
        sweep(URL, ROW)
    assert started == [], "частые касания страницы не гоняют уборку"

    sweep(URL, ("new", *ROW[:-1]))
    assert len(started) == 1


def test_one_sweep_at_a_time(base: _Base) -> None:
    """Касания всех вкладок и старт службы идут через одну сверку, не наперегонки."""
    sweep, started = _inline()
    sweep(URL)
    sweep(URL, ROW)
    assert len(started) == 1

    started.pop()()
    sweep(URL, ROW)
    assert len(started) == 1, "закончилась - следующий ряд сверяется"
