"""Зеркало возврата места: не поднявшийся показ отдаёт сохранённое место прежним."""

from __future__ import annotations

import pytest

from tests.fakes.show_unit import FakeShowUnit
from torrcast.domain.entry import Entry
from torrcast.domain.infra_error import InfraError
from torrcast.ports.state_store.slot import store
from torrcast.usecases.playback.place_kept import place_kept

KEY = "tv:сериал"
PLACE = Entry(title="Сериал", magnet="magnet:?xt=1", kind="tv", season=3, episode=14, pos=546.0)
START = Entry(title="Сериал", magnet="magnet:?xt=1", kind="tv", season=1, episode=1, pos=0.0)


def _started() -> None:
    """Стартовая запись показа уже легла под ключ картины - как в запуске показа."""
    state = store().load()
    state.put(KEY, START)
    store().save(state)


def _saved() -> tuple[int | None, int | None, float]:
    saved = store().load().get(KEY)
    assert saved is not None
    return saved.season, saved.episode, saved.pos


def test_a_show_that_did_not_come_up_gives_the_place_back(show_unit: FakeShowUnit) -> None:
    """🔴 TC-1203. Отказ показа не стоит зрителю места: s3e14 0:09:06 остаётся s3e14."""
    _started()

    with pytest.raises(InfraError), place_kept(KEY, PLACE, lambda: False):
        raise InfraError("показ не запустился")

    assert _saved() == (3, 14, 546.0)


def test_a_show_that_came_up_keeps_its_new_record(show_unit: FakeShowUnit) -> None:
    """Показ поднялся - его запись и есть место, возвращать нечего."""
    _started()

    with place_kept(KEY, PLACE, lambda: False):
        pass

    assert _saved() == (1, 1, 0.0)


def test_a_launch_taken_over_by_another_leaves_the_record_to_it(show_unit: FakeShowUnit) -> None:
    """Подъём снял чужой запуск - состояние пишет он, и откат затёр бы его запись."""
    _started()

    with pytest.raises(InfraError), place_kept(KEY, PLACE, lambda: True):
        raise InfraError("показ отменён")

    assert _saved() == (1, 1, 0.0)


def test_a_show_that_came_up_behind_an_interrupted_wait_keeps_its_record(
    show_unit: FakeShowUnit,
) -> None:
    """Консоль прервали посреди ожидания, а юнит этой картины поднялся и идёт."""
    _started()
    show_unit.alive, show_unit.playing = True, KEY

    with pytest.raises(KeyboardInterrupt), place_kept(KEY, PLACE, lambda: False):
        raise KeyboardInterrupt

    assert _saved() == (1, 1, 0.0)
