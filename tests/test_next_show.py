"""Зеркало перехода на следующую серию: повтор уже сделанного, отказ и экран продолжения."""

from __future__ import annotations

import pytest

from hass.next_show import next_show
from hass.refused_error import NO_NEXT, RefusedError
from tests.fakes.playback_session import FakePlaybackSession
from tests.fakes.state_store import FakeStateStore
from torrcast.domain.entry import Entry
from torrcast.ports.state_store import slot as state_slot


def _series(season: int, episode: int) -> FakePlaybackSession:
    """Идущий сериал с записью на названной серии; следующая в раздаче есть."""
    state_slot.install(FakeStateStore())
    store = state_slot.store()
    state = store.load()
    state.entries["tv:чернобыль"] = Entry(
        title="Чернобыль",
        magnet="magnet:?xt=1",
        kind="tv",
        season=season,
        episode=episode,
        episodes=[[1, 3, 0, 0], [1, 4, 1, 0]],
        query="чернобыль",
    )
    store.save(state)
    return FakePlaybackSession(playing=True, play_key="tv:чернобыль")


def test_a_call_without_an_episode_asks_for_the_next_one_the_old_way() -> None:
    """Home Assistant и стрелка карточки не называют серию - их зов не меняется."""
    assert next_show(_series(1, 3), {})


def test_a_call_naming_an_episode_the_record_has_already_passed_is_a_no_op() -> None:
    """Сторож юнита доиграл сериал сам: запись на s1e4, вкладка доиграла s1e3.

    Второй переход сюда - не просьба, а запоздалый отзвук: ответить на него запуском
    значило бы перепрыгнуть играющую серию (замер на живом приёмнике 10-09-2026).
    """
    assert not next_show(_series(1, 4), {"season": 1, "episode": 3})


def test_a_call_naming_the_episode_the_record_still_shows_advances_from_it() -> None:
    """Запись ещё на кончившейся серии - переход наш, и следующую зовут с неё."""
    assert next_show(_series(1, 3), {"season": 1, "episode": 3})


def test_a_malformed_episode_is_refused_with_the_word_play_uses() -> None:
    with pytest.raises(RefusedError) as refusal:
        next_show(_series(1, 3), {"season": "1", "episode": 3})

    assert refusal.value.word == "bad_episode"


def test_a_half_named_episode_is_refused_too() -> None:
    with pytest.raises(RefusedError) as refusal:
        next_show(_series(1, 3), {"season": 1})

    assert refusal.value.word == "bad_episode"


def test_the_last_episode_refuses_even_when_the_caller_names_it() -> None:
    with pytest.raises(RefusedError) as refusal:
        next_show(_series(1, 4), {"season": 1, "episode": 4})

    assert refusal.value.word == NO_NEXT


def test_nothing_playing_refuses_whatever_the_body_says() -> None:
    session = FakePlaybackSession(playing=False)

    with pytest.raises(RefusedError):
        next_show(session, {"season": 1, "episode": 3})
