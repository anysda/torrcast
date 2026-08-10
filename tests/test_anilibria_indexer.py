"""The optional anime source narrows the catalog instead of breaking search."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "anilibria_indexer", Path(__file__).parents[1] / "scripts/anilibria-indexer.py"
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def test_dead_primary_uses_the_alternative(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def answer(origin: str, path: str) -> Any:
        calls.append(origin)
        if origin == adapter.ORIGINS[0]:
            raise OSError("silent")
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Sonny Boy"}}]
        return [{"label": "Sonny Boy 1080p", "magnet": "magnet:?xt=urn:btih:abc"}]

    monkeypatch.setattr(adapter, "_json", answer)
    assert adapter.search("Sonny Boy")[0]["title"] == "Sonny Boy 1080p"
    assert calls[:2] == list(adapter.ORIGINS)


def test_all_dead_sources_are_an_empty_result(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_json", lambda *_a: (_ for _ in ()).throw(OSError()))
    assert adapter.search("Kaiba") == []


def test_fuzzy_search_cannot_substitute_an_unrelated_release(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def answer(_origin: str, path: str) -> Any:
        if "/search/" in path:
            return [
                {"id": 1, "name": {"english": "Kono Healer, Mendokusai"}},
                {"id": 2, "name": {"english": "Serial Experiments Lain"}},
            ]
        release = path.rsplit("/", 1)[-1]
        return [{"label": f"release {release}", "magnet": f"magnet:?xt=urn:btih:{release}"}]

    monkeypatch.setattr(adapter, "_json", answer)
    assert [row["title"] for row in adapter.search("Serial Experiments Lain")] == ["release 2"]


def test_empty_query_does_not_accept_the_whole_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        adapter,
        "_json",
        lambda *_a: [{"id": 1, "name": {"english": "Kaiba"}}],
    )
    assert adapter.search("") == []
