"""Startup warmup of the disk-cached home screen."""

from __future__ import annotations

import pytest

import web.warm_saved
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.ports.state_store import slot as state_slot
from web.warm_targets import WarmTarget


def _tile(title: str) -> dict[str, object]:
    """A saved shelf tile as ``shelves.json`` keeps it."""
    return {
        "query": title,
        "key": f"movie:{title}:2020",
        "title": title,
        "year": 2020,
        "kind": "movie",
    }


def test_warm_saved_starts_cached_visible_tiles(monkeypatch: pytest.MonkeyPatch) -> None:
    """The service spends its grace period before the first GET /api/shelves."""
    warmed: list[object] = []

    class _Cache:
        def _load(self) -> dict[str, object]:
            return {"built_at": "now", "fresh": [], "popular": []}

        def warm(self, targets: object, later: object) -> None:
            warmed.append((targets, later))

    state_slot.install(FakeStateStore())
    monkeypatch.setattr(web.warm_saved, "_cache", _Cache())

    web.warm_saved.warm_saved()

    assert warmed == [([], [])]


def test_continue_and_the_tiles_after_the_eighth_are_warmed_behind_the_screen(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A Continue tile and the ninth shelf tile are known before a click, so no cold card."""
    warmed: list[tuple[list[WarmTarget], list[WarmTarget]]] = []
    fresh = [_tile(f"New {at}") for at in range(10)]
    popular = [_tile(f"Top {at}") for at in range(9)]

    class _Cache:
        def _load(self) -> dict[str, object]:
            return {"built_at": "now", "fresh": fresh, "popular": popular}

        def warm(self, targets: list[WarmTarget], later: list[WarmTarget]) -> None:
            warmed.append((targets, later))

    fake = FakeStateStore()
    state = fake.load()
    state.entries["movie:inception:2010"] = Entry(
        "Начало", "magnet:a", kind="movie", year=2010, pos=10.0, dur=100.0, updated="2026-02-01"
    )
    state.entries["movie:done:2011"] = Entry(
        "Done", "magnet:b", kind="movie", year=2011, pos=100.0, dur=100.0, updated="2026-03-01"
    )
    fake.save(state)
    state_slot.install(fake)
    monkeypatch.setattr(web.warm_saved, "_cache", _Cache())

    web.warm_saved.warm_saved()

    [(screen, later)] = warmed
    assert len(screen) == 16
    assert [target[2] for target in later] == ["Начало", "New 8", "Top 8", "New 9"]
