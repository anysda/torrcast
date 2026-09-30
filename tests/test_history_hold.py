"""Запрос истории заводит первые записи «Продолжить», не дожидаясь зова плиток."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import web.history as history_module
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.continue_row import WARM_ROW
from torrcast.domain.entry import Entry
from torrcast.ports.state_store import slot as state_slot
from web.history import history
from web.request import Request


@pytest.fixture(autouse=True)
def _posters(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(history_module, "hits", SimpleNamespace(offer=lambda records: records))


def _row(count: int) -> list[str]:
    fake = FakeStateStore()
    state = fake.load()
    for n in range(count):
        state.entries[f"movie:m{n}:2020"] = Entry(
            f"M{n}",
            f"magnet:m{n}",
            kind="movie",
            pos=10.0,
            dur=100.0,
            updated=f"2026-01-{n + 1:02d}",
        )
    state.entries["movie:done:2020"] = Entry(
        "Done", "magnet:done", kind="movie", pos=100.0, dur=100.0, updated="2026-12-01"
    )
    fake.save(state)
    state_slot.install(fake)
    return [f"movie:m{n}:2020" for n in reversed(range(count))]


def test_the_history_request_holds_the_first_records_of_the_row(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    row = _row(WARM_ROW + 2)
    touched: list[tuple[str, list[str]]] = []

    def touch(url: str, keys: list[str]) -> int:
        touched.append((url, keys))
        return 0

    hold = SimpleNamespace(touch=touch)
    monkeypatch.setattr(history_module, "RECORD_HOLD", hold)
    monkeypatch.setattr(history_module, "load_config", lambda: SimpleNamespace(torrserver_url="ts"))

    assert history(Request("GET", "/api/history", {}, {})).code == 200

    assert touched == [("ts", row[:WARM_ROW])]
