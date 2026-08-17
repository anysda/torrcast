"""Хранилище за портом: имена договора поверх того же файла и той же раскладки."""

from __future__ import annotations

from pathlib import Path

import pytest

from torrcast.adapters.filesystem.state.file_state_store import FileStateStore
from torrcast.adapters.filesystem.state.state import State
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState


@pytest.fixture(autouse=True)
def _own_file(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))


def test_the_store_writes_the_very_same_file_the_state_reads() -> None:
    """Раскладка одна на обе стороны: разойдись они, показ читал бы не то, что писал."""
    store = FileStateStore()

    store.save(WatchState({"фильм": Entry("Моана", "magnet:?xt=1", pos=42.0)}))

    assert State.load().entries["фильм"].pos == 42.0
    assert store.load().entries["фильм"].pos == 42.0


def test_every_load_rereads_the_file_because_another_leg_of_the_show_writes_it() -> None:
    """Хранилище не кэширует: рядом пишет второй процесс, и его запись обязана быть видна."""
    store = FileStateStore()
    store.save(WatchState({"фильм": Entry("Моана", "magnet:?xt=1", pos=1.0)}))
    first = store.load()

    State({"фильм": Entry("Моана", "magnet:?xt=1", pos=2.0)}).save()

    assert first.entries["фильм"].pos == 1.0
    assert store.load().entries["фильм"].pos == 2.0
