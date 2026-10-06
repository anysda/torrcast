"""Закладка карточки: какую раздачу продолжит «Играть»."""

from __future__ import annotations

from typing import Any

from torrcast.domain.entry import Entry
from web.bookmark import bookmark

_HASH = "b" * 40


def _live(**rest: Any) -> Entry:
    fields = {
        "title": "Film",
        "magnet": "magnet:?xt=urn:btih:" + _HASH,
        "dur": 7200.0,
        "pos": 180.0,
    }
    return Entry(**{**fields, **rest})


def test_a_started_film_is_continued_and_a_finished_one_is_not() -> None:
    assert bookmark(_live()) == (_HASH, "")
    assert bookmark(_live(done=True)) == ("", "")
    assert bookmark(None) == ("", "")
