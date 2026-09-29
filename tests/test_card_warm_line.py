"""Карточка из истории берёт согретый круг картины, а не идёт в сеть строкой-слагом."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes.state_store import FakeStateStore
from tests.test_card import _MOVIE, _MOVIE_PLAN, _PROBE_FACTS, _asked, _by_query, _warm, _wired
from torrcast.ports.state_store import slot as state_slot


def test_a_history_tile_plays_the_circle_warmed_under_the_picture_title(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """«Рататуй»: плитка несёт «рататуй», круг согрет под «Рататуй»; сеть стоила 7-8 с."""
    asked: list[str] = []
    found = _by_query({"Own Title Probe": [_MOVIE_PLAN], "own-title-probe": [_MOVIE_PLAN]})

    def circle(query: str, **_k: object) -> Any:
        asked.append(query)
        return found(query)

    warm = _warm(circle)
    _wired(monkeypatch, [])
    monkeypatch.setattr("web.card.WARM", warm)
    monkeypatch.setattr("web.card.preview", lambda *_args: None)
    state_slot.install(FakeStateStore())
    warm.take("Own Title Probe")

    code, body, _extra = _asked(_MOVIE.key, query="own-title-probe", extra_query=_PROBE_FACTS)

    assert (code, body["picture"], body["query"]) == (200, _MOVIE.key, "Own Title Probe")
    assert asked == ["Own Title Probe"]
