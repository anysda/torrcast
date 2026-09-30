"""Сверка базы службы с рядом идёт фоном и уступает показу."""

from __future__ import annotations

import threading
from typing import Any

import pytest

import web.sweep_later as module
from tests.fakes.state_store import FakeStateStore
from tests.test_record_sweep import _Base, _entries, _hash
from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.watch_state import WatchState
from torrcast.ports.state_store import slot as state_slot


class _Journal:
    def __init__(self) -> None:
        self.marks: list[tuple[str, dict[str, Any]]] = []

    def mark(self, what: str, **facts: Any) -> None:
        self.marks.append((what, facts))


@pytest.fixture
def base(monkeypatch: pytest.MonkeyPatch) -> _Base:
    store = FakeStateStore()
    store.save(WatchState(_entries(WARM_ROW + 2)))
    state_slot.install(store)
    found = _Base({_hash(n) for n in range(WARM_ROW + 2)})
    monkeypatch.setattr(module, "TorrServer", lambda url, timeout: found)
    monkeypatch.setattr(module, "_showing", lambda: False)
    monkeypatch.setattr(module, "_held_by_show", lambda torrent_hash: False)
    return found


def test_the_sweep_runs_in_its_own_thread_and_is_journaled(
    base: _Base, monkeypatch: pytest.MonkeyPatch
) -> None:
    journal = _Journal()
    monkeypatch.setattr(module, "journal", lambda: journal)
    started: list[threading.Thread] = []
    monkeypatch.setattr(threading.Thread, "start", lambda self: started.append(self))

    module.sweep_later("http://ts")
    started[0].run()

    assert started[0].daemon
    assert sorted(base.dropped) == [_hash(WARM_ROW), _hash(WARM_ROW + 1)]
    assert journal.marks == [("уборка записей", {"снесено": 2})]


def test_a_live_show_leaves_the_service_alone(base: _Base, monkeypatch: pytest.MonkeyPatch) -> None:
    """Список и снос шли бы по той же службе, что отдаёт кадры показу."""
    monkeypatch.setattr(module, "_showing", lambda: True)

    module._sweep_records("http://ts")

    assert base.dropped == []


def test_a_silent_service_is_left_for_the_next_touch(
    base: _Base, monkeypatch: pytest.MonkeyPatch
) -> None:
    def silent() -> set[str]:
        raise TorrcastError("TorrServer не ответил")

    monkeypatch.setattr(base, "hashes", silent)

    module._sweep_records("http://ts")

    assert base.dropped == []
