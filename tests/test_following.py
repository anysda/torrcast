"""Зеркало запроса следующей серии: что скажет ``entry.advance``, то и станет запросом."""

from __future__ import annotations

from hass.following import following
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
