"""Зеркало запроса следующей серии: что скажет ``entry.advance``, то и станет запросом."""

from __future__ import annotations

import pytest

import hass.following as following_module
from hass.following import following, waits_for_next
from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.ports.state_store import slot as state_slot


def test_nothing_playing_has_no_next_episode() -> None:
    assert following(FakePlaybackSession(playing=False)) is None


def test_a_film_has_no_next_episode() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["movie:муха"] = Entry(title="Муха", magnet="magnet:?xt=1", kind="movie")
    store.save(state)

    assert following(FakePlaybackSession(playing=True, play_key="movie:муха")) is None


def test_the_next_episode_is_asked_for_by_the_query_a_human_would_type() -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=3,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)

    assert following(FakePlaybackSession(playing=True, play_key="tv:чернобыль")) == "чернобыль s1e4"


def test_past_the_last_episode_of_the_release_the_catalogue_names_the_next(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:рик"] = Entry(
        title="Рик и Морти",
        magnet="magnet:?xt=1",
        kind="tv",
        season=8,
        episode=3,
        episodes=[[8, 3, 0, 0]],
        query="rick and morty",
    )
    store.save(state)
    asked: list[tuple[int | None, int | None, str, str]] = []

    def catalogue(entry: Entry, key: str, query: str) -> str | None:
        asked.append((entry.season, entry.episode, key, query))
        return "s8e4"

    monkeypatch.setattr(following_module, "catalog_next", catalogue)

    said = following(FakePlaybackSession(playing=True, play_key="tv:рик"))

    assert said == "rick and morty s8e4"
    assert asked == [(8, 3, "tv:рик", "rick and morty")], "пул спрашивается кругом запроса"


def test_inside_the_release_the_catalogue_is_not_asked(monkeypatch: pytest.MonkeyPatch) -> None:
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=1,
        episode=3,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    monkeypatch.setattr(following_module, "catalog_next", lambda *_a: "s9e9")

    assert following(FakePlaybackSession(playing=True, play_key="tv:чернобыль")) == "чернобыль s1e4"


def test_a_tvmaze_question_at_the_end_waits_for_the_units_search(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_slot.install(FakeStateStore())
    state = state_slot.store().load()
    state.entries["tv:рик"] = Entry(
        title="Рик и Морти", magnet="m", kind="tv", season=9, episode=5,
        episodes=[[9, 5, 0, 0]], query="rick and morty",
    )  # fmt: skip
    state_slot.store().save(state)
    monkeypatch.setattr(following_module, "catalog_next", lambda *_a: None)
    monkeypatch.setattr(following_module, "catalog_waits", lambda *_a: True)
    session = FakePlaybackSession(playing=True, play_key="tv:рик")

    assert following(session) is None
    assert waits_for_next(session) is True
