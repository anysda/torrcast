"""Startup warmup of the disk-cached home screen."""

from __future__ import annotations

import web.warm_saved


def test_warm_saved_starts_cached_visible_tiles(monkeypatch: object) -> None:
    """The service spends its grace period before the first GET /api/shelves."""
    warmed: list[object] = []

    class _Cache:
        def _load(self) -> dict[str, object]:
            return {"built_at": "now", "fresh": [], "popular": []}

        def warm(self, targets: object) -> None:
            warmed.append(targets)

    monkeypatch.setattr(web.warm_saved, "_cache", _Cache())  # type: ignore[attr-defined]

    web.warm_saved.warm_saved()

    assert warmed == [[]]
