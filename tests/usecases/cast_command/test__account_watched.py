"""Зеркало бухгалтерии досмотра: когда закладка становится «досмотрено» и что она говорит."""

from __future__ import annotations

import pytest

from tests.usecases.cast_command.world import entry
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.watch_state import WatchState
from torrcast.usecases.cast_command._account_watched import _account_watched


def test_a_watched_bookmark_becomes_watched_on_the_next_cast(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Закладка за порогом досмотра на следующем ``cast`` превращается в «досмотрено»."""
    state = WatchState()
    saved = entry(pos=7000.0)
    state.put("кино", saved)

    (key, following), moved = _account_watched(state, ("кино", saved))

    assert moved is True and key == "кино"
    assert following.pos == 0.0, "с начала - это ноль, а не прежнее место"
    line = phrase(
        "account_watched.done",
        title="Кино",
        what="",
        stopped="1:56:40",
        dur="2:00:00",
        decision=phrase("account_watched.from_start"),
    )
    assert line in capsys.readouterr().out


def test_an_unfinished_bookmark_is_left_alone() -> None:
    """Место, до порога не доехавшее, - это место, а не досмотр."""
    state = WatchState()
    saved = entry(pos=100.0)
    state.put("кино", saved)

    found, moved = _account_watched(state, ("кино", saved))

    assert moved is False and found[1] is saved


def test_a_bookmark_where_the_show_died_at_the_tail_is_not_counted(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """🔴 Показ погас у конца без отданного хвоста (:meth:`Watch.cut`): закладка за долей -
    это место обрыва, и следующий ``cast`` продолжает с него, а не зовёт серию досмотренной.

    Отрицательная проба: убрать условие ``entry.dark`` - закладка уходит в «досмотрено».
    """
    state = WatchState()
    saved = entry(pos=7000.0)
    saved.dark, saved.dark_why = 1_700_000_000.0, "хвост не отдан"
    state.put("кино", saved)

    found, moved = _account_watched(state, ("кино", saved))

    assert moved is False and found[1] is saved
    assert capsys.readouterr().out == ""


def test_a_viewer_who_stopped_at_96_percent_still_gets_it_counted() -> None:
    """Человек сам остановил на 96 %: отметки темноты нет, и правило закладки прежнее -
    за 95 % это «досмотрено» (README, «Сериалы»; TC-882)."""
    state = WatchState()
    saved = entry(pos=7200.0 * 0.96)
    state.put("кино", saved)

    _found, moved = _account_watched(state, ("кино", saved))

    assert moved is True
