"""Холодное сохранённое тело метит ответ сборкой с первого запроса, и метка не виснет."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path

import pytest

from tests.test_shelf_pass import _cache as _pass_cache
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.infra_error import InfraError
from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.cold import cold
from web.shelf_pass import ShelfPass
from web.shelves_cache import ShelvesCache

_TILE: JsonValue = {"key": "movie:матрица:2026", "title": "Матрица"}


def _body(**shelves: list[JsonValue]) -> dict[str, JsonValue]:
    return {FIELD: RULE, "built_at": "2026-09-30T08:00:00+00:00", **shelves}


def _silent_feed(_limit: int) -> list[FeedRow]:
    raise InfraError("indexers are silent")


def _cache(
    tmp_path: Path, body: dict[str, JsonValue], jobs: list[Callable[[], None]]
) -> ShelvesCache:
    path = tmp_path / "shelves.json"
    path.write_text(json.dumps(body, ensure_ascii=False), encoding="utf-8")
    return ShelvesCache(
        feed=_silent_feed,
        catalogue=torrent_catalogue,
        offer=lambda records: records,
        path=path,
        attempts=1,
        sleep=lambda _seconds: None,
        spawn=jobs.append,
        early=True,
    )


def test_a_body_without_a_shelf_or_built_by_another_rule_is_cold() -> None:
    assert cold(_body(fresh=[_TILE], popular=[]))
    assert cold({**_body(fresh=[_TILE], popular=[_TILE]), FIELD: RULE - 1})
    assert cold({})
    assert not cold(_body(fresh=[_TILE], popular=[_TILE]))


def test_a_saved_half_body_marks_the_first_answer_before_the_feed_answers(
    tmp_path: Path,
) -> None:
    jobs: list[Callable[[], None]] = []
    cache = _cache(tmp_path, _body(fresh=[_TILE], popular=[]), jobs)

    cache.get()  # the service start: the feed has not answered yet

    assert (cache.filling, cache.settling) == (True, True)
    cache._pass()  # every indexer silent: the pass gives up
    assert (cache.filling, cache.settling) == (False, False)
    assert len(jobs) == 1


def test_a_whole_body_of_this_rule_starts_without_the_mark(tmp_path: Path) -> None:
    jobs: list[Callable[[], None]] = []
    cache = _cache(tmp_path, _body(fresh=[_TILE], popular=[_TILE]), jobs)

    cache.get()

    assert (cache.filling, cache.settling) == (False, False)


def _retry_marks(
    tmp_path: Path, plays: bool, cache: ShelvesCache | None = None
) -> list[tuple[bool, bool]]:
    cache = cache or _pass_cache(tmp_path, 3)
    cache.attempts = 2
    marks: list[tuple[bool, bool]] = []
    cache.sleep = lambda _pause: marks.append((cache.filling, cache.settling))
    cache.playable = lambda _query, _key: plays
    cache._pass()
    assert (cache.filling, cache.settling) == (False, False)
    return marks


def test_an_empty_shelf_keeps_the_mark_through_the_next_feed_attempt(tmp_path: Path) -> None:
    """Rollback (the pass clears the mark): the page stops asking and stays on the empty shelf."""
    assert _retry_marks(tmp_path, plays=False) == [(True, True)]


def test_whole_shelves_drop_the_mark_and_ask_the_feed_no_more(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Rollback (the mark kept to the build's end): the counter hangs over full shelves.

    Past «ready» the shelf only shrinks (:mod:`web.ready_shelf`): no next attempt to wait for.
    """
    cache = _pass_cache(tmp_path, 3)
    marks: list[tuple[bool, bool]] = []
    run = ShelfPass.run

    def spy(shelf: ShelfPass) -> dict[str, JsonValue]:
        body = run(shelf)
        marks.append((cache.filling, cache.settling))
        return body

    monkeypatch.setattr(ShelfPass, "run", spy)

    assert _retry_marks(tmp_path, plays=True, cache=cache) == []
    assert marks == [(False, False)]
