"""Карточка одной картины: собранное тело и заголовок недоехавшей части."""

from __future__ import annotations

import json
from typing import Any

import pytest

from tests.fakes.state_store import FakeStateStore
from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.release import Release
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.state_store import slot as state_slot
from torrcast.usecases.select.plan import Plan
from web.answer import JSON
from web.card import card
from web.request import Request

_MOVIE = Picture(title="Interstellar", year=2014, kind="movie", original="Interstellar")
_LEAD = Release(
    raw_name="Interstellar 2014 BDRip 1080p LostFilm",
    title="Interstellar",
    quality="1080p",
    seeders=100,
)
_OTHER = Release(
    raw_name="Interstellar 2014 BDRip 720p AlexFilm",
    title="Interstellar",
    quality="720p",
    seeders=50,
)
_MOVIE.releases = [_LEAD, _OTHER]
_MOVIE_PLAN = Plan(
    picture=_MOVIE, ranked=[_LEAD], runtime=8520.0, warn_mbit=12.0, runtime_estimated=False
)

_SHOW = Picture(title="Show", year=2022, kind="tv")
_SHOW_RELEASE = Release(
    raw_name="Show s01 WEB-DL 1080p LostFilm",
    title="Show",
    quality="1080p",
    seeders=40,
    seasons=(1, 2),
)
_SHOW.releases = [_SHOW_RELEASE]
_SHOW_PLAN = Plan(picture=_SHOW, ranked=[_SHOW_RELEASE], runtime=1500.0, warn_mbit=12.0)


def _plans(plans: list[Plan]) -> Any:
    def _search(*_a: object, **_k: object) -> list[Plan]:
        return plans

    return _search


def _wired(monkeypatch: pytest.MonkeyPatch, plans: list[Plan]) -> None:
    monkeypatch.setattr("web.card.load_config", lambda: Config())
    monkeypatch.setattr("web.card.detector", _Detector())
    monkeypatch.setattr("web.card.search_circle", _plans(plans))


class _Detector:
    def detect(self, _config: Config) -> Choice:
        return Choice(CAUTIOUS, "тест")


def _asked(key: str, query: str = "interstellar") -> tuple[int, dict[str, Any], tuple[str, ...]]:
    answer = card(Request("GET", f"/api/card/{key}", {"query": query}, {}))
    assert answer.kind == JSON
    body: dict[str, Any] = json.loads(answer.body)
    return answer.code, body, tuple(name for name, _ in answer.extra)


def test_no_query_is_refused_before_any_search_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(*_a: object, **_k: object) -> list[Plan]:
        raise AssertionError("поиск не должен звать при пустом query")

    _wired(monkeypatch, [])
    monkeypatch.setattr("web.card.search_circle", _boom)

    answer = card(Request("GET", f"/api/card/{_MOVIE.key}", {}, {}))

    assert answer.code == 400
    assert json.loads(answer.body) == {"error": "no_query"}


def test_an_unknown_key_is_a_404_not_a_crash(monkeypatch: pytest.MonkeyPatch) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked("movie:nobody:1900")

    assert code == 404
    assert body == {"error": "not_found"}


def test_a_search_refusal_surfaces_as_409_with_the_products_own_word(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _refused(*_a: object, **_k: object) -> list[Plan]:
        raise TorrcastError("nothing_found")

    _wired(monkeypatch, [])
    monkeypatch.setattr("web.card.search_circle", _refused)

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 409
    assert body["error"] == "nothing_found"


def test_a_movie_card_names_its_voices_by_studio_not_by_a_bare_bool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_MOVIE.key)

    assert code == 200
    assert body["title"] == "Interstellar"
    assert body["kind"] == "movie"
    assert body["runtime"] == 8520.0
    assert body["runtime_estimated"] is False
    assert body["seasons"] == []
    voices = {voice["name"]: voice for voice in body["voices"]}
    assert voices.keys() == {"LostFilm", "AlexFilm"}
    assert voices["LostFilm"]["quality"] == "1080p"
    assert voices["LostFilm"]["default"] is True
    assert voices["AlexFilm"]["default"] is False
    assert body["releases_count"] == 2


def test_the_partial_header_appears_until_the_facts_cache_has_something(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_MOVIE_PLAN])
    state_slot.install(FakeStateStore())
    monkeypatch.setenv("TORRCAST_STATE", "/nonexistent-so-facts-cache-stays-empty")

    _code, body, extra = _asked(_MOVIE.key)

    assert body["blurb"] is None
    assert body["rating"] is None
    assert "X-Torrcast-Partial" in extra


def test_a_series_without_a_bookmark_only_counts_seasons_from_release_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_SHOW_PLAN])
    state_slot.install(FakeStateStore())

    code, body, _extra = _asked(_SHOW.key, query="show")

    assert code == 200
    assert body["seasons"] == [{"n": 1, "episodes": []}, {"n": 2, "episodes": []}]
    assert body["resumable"] is False
    assert body["label"] == ""


def test_a_series_with_a_bookmark_marks_earlier_episodes_watched(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _wired(monkeypatch, [_SHOW_PLAN])
    fake = FakeStateStore()
    state = fake.load()
    state.entries[_SHOW.key] = Entry(
        "Show",
        "magnet:show",
        kind="tv",
        season=1,
        episode=2,
        pos=30.0,
        dur=1200.0,
        episodes=[[1, 1, 0, 0], [1, 2, 1, 0]],
    )
    fake.save(state)
    state_slot.install(fake)

    code, body, _extra = _asked(_SHOW.key, query="show")

    assert code == 200
    assert body["label"] == "s1e2"
    assert body["resumable"] is True
    season_one = next(season for season in body["seasons"] if season["n"] == 1)
    by_episode = {episode["n"]: episode for episode in season_one["episodes"]}
    assert by_episode[1]["watched"] is True
    assert by_episode[1]["pos"] == 0.0
    assert by_episode[2]["watched"] is False
    assert by_episode[2]["pos"] == 30.0
