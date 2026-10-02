"""Плитка, выросшая в ряду после первого показа, встаёт вместе со своей обложкой.

Страница кладёт обложку в стоящую плитку только одной общей пачкой, поэтому сервер
придерживает новую плитку, пока её обложка в пути, но не дольше :data:`GROWN_BY`.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from hass.search_first_screen import GROWN_BY, search_first_screen
from hass.search_job import SearchJob
from torrcast.domain.json_value import JsonValue

A: JsonValue = {"key": "a", "title": "Alpha"}
B: JsonValue = {"key": "b", "title": "Beta"}


class _Covers:
    """Обложки в пути ровно у названных ключей; байтов не лежит ни у кого."""

    def __init__(self, coming: set[str]) -> None:
        self.coming = coming

    def landed(self, record: JsonValue) -> bool:
        return False

    def has(self, name: str) -> bool:
        return False

    def pending(self, records: Sequence[JsonValue]) -> bool:
        return any(isinstance(one, dict) and one.get("key") in self.coming for one in records)

    def due(self, records: Sequence[JsonValue]) -> bool:
        return False


def _keys(shown: list[Any]) -> list[str]:
    return [hit["key"] for hit in shown]


def _drawn(covers: _Covers) -> SearchJob:
    """Заход, чей первый ряд уже на экране; приговор о картинке ``a`` вынесен."""
    job = SearchJob()
    job.posters["a"] = {}
    assert _keys(search_first_screen(job, [A], covers)) == ["a"], "первый ряд не встал"
    return job


def test_a_grown_tile_waits_for_its_cover() -> None:
    covers = _Covers({"b"})
    job = _drawn(covers)
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a"], "плитка встала голой"
    job.posters["b"] = {}
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a"], "байты ещё в пути"
    covers.coming.clear()
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a", "b"]


def test_a_grown_tile_waits_only_until_its_deadline() -> None:
    covers = _Covers({"b"})
    job = _drawn(covers)
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a"]
    job.appeared["b"] -= GROWN_BY
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a", "b"], "плитку держат вечно"


def test_a_tile_once_shown_is_never_held_again() -> None:
    covers = _Covers(set())
    job = _drawn(covers)
    job.posters["b"] = {}
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a", "b"]
    covers.coming.add("b")
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a", "b"], "плитка ушла с экрана"


def test_the_final_answer_is_not_held() -> None:
    covers = _Covers({"b"})
    job = _drawn(covers)
    job.done = True
    assert _keys(search_first_screen(job, [A, B], covers)) == ["a", "b"]
