"""The optional Russian catalog source degrades to an empty result."""

import importlib.util
from pathlib import Path
from typing import Any

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_indexer", Path(__file__).parents[1] / "scripts/jacred-indexer.py"
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def test_public_rows_become_cardigann_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    answer: dict[str, Any] = {
        "results": [
            {
                "title": "Матрица 1999 1080p Dub",
                "magnet": "magnet:?xt=urn:btih:" + "a" * 40,
                "size": 8_000_000_000,
                "seeders": 42,
                "peers": 3,
                "created_at": "2026-08-11",
            }
        ]
    }
    monkeypatch.setattr(adapter, "_json", lambda *_a: answer)
    (row,) = adapter.search("матрица")
    assert row["title"] == "Матрица 1999 1080p Dub"
    assert row["seeders"] == 42
    assert row["leechers"] == 3


def test_dead_api_is_an_empty_optional_source(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_json", lambda *_a: (_ for _ in ()).throw(OSError()))
    assert adapter.search("матрица") == []


def test_empty_query_does_not_dump_the_catalog(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(adapter, "_json", lambda *_a: pytest.fail("API must not be called"))
    assert adapter.search("") == []
