"""The optional Russian catalog source degrades to an empty result."""

import importlib.util
import subprocess
from pathlib import Path
from typing import Any, NoReturn

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_indexer", Path(__file__).parents[1] / "scripts/jacred-indexer.py"
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _raise(error: BaseException) -> Any:
    """A fetch that only ever fails: the API is dead in the way the test names."""

    def fetch(*_args: str) -> NoReturn:
        raise error

    return fetch


def test_public_rows_become_cardigann_rows() -> None:
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
    (row,) = adapter.search("матрица", lambda *_a: answer)
    assert row["title"] == "Матрица 1999 1080p Dub"
    assert row["seeders"] == 42
    assert row["leechers"] == 3


def test_dead_api_is_an_empty_optional_source() -> None:
    assert adapter.search("матрица", _raise(OSError())) == []


def test_a_hung_api_is_an_empty_source_and_not_a_dropped_connection() -> None:
    """A stall is how this API usually dies, and it does not arrive as OSError:
    `subprocess.run` raises its own TimeoutExpired, which descends from SubprocessError.
    Uncaught it leaves the handler as a dropped connection, and Prowlarr answers a dropped
    connection with a ban ladder - one dead source would then cost the whole search
    instead of narrowing the catalog."""
    assert adapter.search("матрица", _raise(subprocess.TimeoutExpired("curl", 4.0))) == []


def test_empty_query_does_not_dump_the_catalog() -> None:
    def fetch(*_args: str) -> Any:
        pytest.fail("API must not be called")

    assert adapter.search("", fetch) == []
