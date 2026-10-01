"""Ряд «Продолжить» метит ответ, пока его обложки ещё могут доехать."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

import web.history as history_module
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.domain.json_value import JsonValue
from torrcast.ports.state_store import slot as state_slot
from web.history import history
from web.request import Request


def _bookmarked() -> None:
    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:one:2026"] = Entry(
        "Один", "magnet:one", kind="movie", pos=10.0, dur=100.0, updated="2026-01-01"
    )
    fake.save(state)
    state_slot.install(fake)


def _headers(monkeypatch: pytest.MonkeyPatch, coming: bool) -> dict[str, str]:
    seen: list[list[JsonValue]] = []

    def _pending(records: list[JsonValue]) -> bool:
        seen.append(records)
        return coming

    fake = SimpleNamespace(offer=lambda records, ahead=False: records, pending=_pending)
    monkeypatch.setattr(history_module, "hits", fake)
    monkeypatch.setattr(history_module, "hold_first", lambda keys: None)
    _bookmarked()
    answer = history(Request("GET", "/api/history", {}, {}))
    assert answer.code == 200
    assert len(seen) == 1 and len(seen[0]) == 1, "метку решает сам ответ, а не пустой список"
    return dict(answer.extra)


def test_history_is_marked_partial_while_a_cover_may_still_come(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Шторм 429 дольше тишины: обложка отложена, и страница должна переспросить."""
    assert _headers(monkeypatch, coming=True).get("X-Torrcast-Partial") == "1"


def test_settled_history_carries_no_partial_mark(monkeypatch: pytest.MonkeyPatch) -> None:
    """Приговоры сказаны: страница не переспрашивает зря."""
    assert "X-Torrcast-Partial" not in _headers(monkeypatch, coming=False)
