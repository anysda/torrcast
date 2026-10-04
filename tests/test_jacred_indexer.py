"""The optional Russian catalog source degrades to an empty result."""

import importlib.util
import subprocess
import threading
import time
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
    # Unix seconds: Prowlarr spent ~40 ms of CPU a row guessing the format of "2026-08-11".
    assert row["date"] == "1786406400"


def test_a_release_day_out_of_shape_is_the_epoch() -> None:
    answer = {
        "results": [
            {"title": "t", "magnet": "m", "created_at": "вчера"},
            {"title": "u", "magnet": "n"},
        ]
    }
    assert [row["date"] for row in adapter.search("t", lambda *_a: answer)] == ["0", "0"]


def test_jacred_seasons_are_carried_in_a_parseable_title_marker() -> None:
    answer: dict[str, Any] = {
        "results": [
            {
                "title": "Сериал WEB-DL 1080p",
                "magnet": "magnet:?xt=urn:btih:" + "b" * 40,
                "seasons": [1, 2],
            }
        ]
    }

    (row,) = adapter.search("сериал", lambda *_a: answer)

    assert row["title"] == "Сериал WEB-DL 1080p [Сезон: 1, 2]"


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


def _rows(*keys: str) -> dict[str, Any]:
    return {"results": [{"title": key, "magnet": "magnet:?xt=urn:btih:" + key} for key in keys]}


def test_joined_names_are_asked_apart_and_answered_together() -> None:
    answers = {"Тачки 2006": _rows("a1", "a2", "both"), "Cars 2006": _rows("both", "b1")}
    asked: list[str] = []

    def fetch(_origin: str, query: str) -> Any:
        asked.append(query)
        return answers[query]

    rows = adapter.search("Тачки 2006 | Cars 2006", fetch)
    assert sorted(asked) == ["Cars 2006", "Тачки 2006"]
    assert [row["title"] for row in rows] == ["a1", "both", "a2", "b1"]


def test_a_slow_name_does_not_hold_the_viewer_s_text() -> None:
    """The first text is the viewer's: a name past the grace is left, one inside it kept."""
    free = threading.Event()
    answers = {"Тачки 2006": _rows("a1"), "Cars 2006": _rows("b1"), "Cars 2006 slow": _rows("c1")}

    def fetch(_origin: str, query: str) -> Any:
        if query.endswith("slow"):
            free.wait(5.0)
        return answers[query]

    began = time.monotonic()
    rows = adapter.search("Тачки 2006 | Cars 2006 | Cars 2006 slow", fetch, grace=0.2)
    took = time.monotonic() - began
    free.set()
    assert took < 2.0, "the slow name held the answer"
    assert [row["title"] for row in rows] == ["a1", "b1"]


@pytest.mark.machine
def test_the_names_leave_only_once_the_viewer_s_text_has_answered() -> None:
    """The API slows and refuses texts that come at once: the viewer's goes alone."""
    events: list[str] = []

    def fetch(_origin: str, query: str) -> Any:
        events.append("ask " + query)
        time.sleep(0.05)
        events.append("got " + query)
        return _rows(query)

    adapter.search("Тачки | Тачки 2006 | Cars 2006", fetch)
    assert events[:2] == ["ask Тачки", "got Тачки"], events


def test_the_joint_is_the_one_torrcast_sends() -> None:
    from torrcast.domain.joint_query import JOINT

    assert adapter.JOINT == JOINT
