"""The optional anime source narrows the catalog instead of breaking search."""

import importlib.util
import subprocess
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


def test_hung_sources_are_an_empty_result_and_not_a_dropped_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A stall is how this source usually dies, and it does not arrive as OSError:
    `subprocess.run` raises its own TimeoutExpired, which descends from SubprocessError.
    Uncaught it leaves the handler as a dropped connection, and Prowlarr answers a dropped
    connection with a ban ladder - the step for a source that does not answer is a whole
    day, so one stall would cost the whole search instead of narrowing the catalog."""
    monkeypatch.setattr(
        adapter,
        "_json",
        lambda *_a: (_ for _ in ()).throw(subprocess.TimeoutExpired("curl", 4.0)),
    )
    assert adapter.search("Kaiba") == []


def test_a_release_that_hangs_on_details_only_drops_itself(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The details of a release are asked for after the listing answered, so a stall there
    reaches a second catch - and it too owes the caller rows, not a broken connection."""

    def answer(_origin: str, path: str) -> Any:
        if "/search/" in path:
            return [{"id": 7, "name": {"english": "Kaiba"}}]
        raise subprocess.TimeoutExpired("curl", 4.0)

    monkeypatch.setattr(adapter, "_json", answer)
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
