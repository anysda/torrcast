"""Начало отсчёта ползунка: чистая функция, из которой ползунок никогда не пятится."""

from __future__ import annotations

from datetime import datetime, timedelta

from custom_components.torrcast.mark_position import mark_position

#: Миг, когда закладка была снята, и миг, когда пришёл следующий ответ серва.
SINCE = datetime(2026, 9, 5, 12, 0, 0)
NOW = SINCE + timedelta(seconds=5)


def test_a_bookmark_that_stood_still_keeps_the_origin_where_it_was() -> None:
    """Повторное место - не новое измерение: показ пишет закладку раз в десять секунд,
    а опрос спрашивает раз в пять, и штамп времени на каждом ответе гнал ползунок
    вперёд, а потом ронял обратно.
    """
    assert mark_position(12.0, playing=True, known=12.0, since=SINCE, now=NOW) == (12.0, SINCE)


def test_a_bookmark_that_moved_takes_the_origin_with_it_by_exactly_as_much() -> None:
    """Закладка прибавила 4 с - начало отсчёта уезжает ровно на 4 с, а не на 5 с стены.

    Отставание тут и рождается, и оно намеренное: рисуемое число не должно прыгнуть.
    """
    place, mark = mark_position(16.0, playing=True, known=12.0, since=SINCE, now=NOW)

    assert place == 16.0
    assert mark == SINCE + timedelta(seconds=4)


def test_a_bookmark_that_ran_ahead_of_the_wall_clock_stops_at_now() -> None:
    """Перемотка вперёд: начало отсчёта доходит до `now` и дальше не уезжает."""
    assert mark_position(112.0, playing=True, known=12.0, since=SINCE, now=NOW) == (112.0, NOW)


def test_a_seek_backwards_re_anchors_the_origin_outright() -> None:
    """Место уехало назад - прежнее отставание к нему неприложимо вовсе."""
    assert mark_position(3.0, playing=True, known=12.0, since=SINCE, now=NOW) == (3.0, NOW)


def test_a_show_that_is_not_playing_re_anchors_the_origin() -> None:
    """Пауза не тикает: карточка рисует само место, и падать оттуда нечему."""
    assert mark_position(12.0, playing=False, known=12.0, since=SINCE, now=NOW) == (12.0, NOW)


def test_the_first_answer_has_nothing_to_lag_behind() -> None:
    """Закладки на руках ещё нет - начало отсчёта берётся мигом ответа."""
    assert mark_position(12.0, playing=True, known=None, since=SINCE, now=NOW) == (12.0, NOW)


def test_a_snapshot_without_a_position_forgets_the_bookmark() -> None:
    """Поля нет вовсе: помнить нечего, и ползунок с карточки пропадает целиком."""
    assert mark_position(None, playing=True, known=12.0, since=SINCE, now=NOW) == (None, NOW)
