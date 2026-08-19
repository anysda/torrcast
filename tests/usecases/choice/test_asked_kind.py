"""Зеркало :mod:`torrcast.usecases.choice.asked_kind`: тип, названный самим запросом.

Тип назван вслух ровно одним способом - запрос спросил СЕРИЮ. Тогда одноимённая
полнометражка не «вариант поживее», а другое кино, и считать дефолт обязаны среди
сериалов. Замер по живой выдаче: «хорошая жена s1e1» ставила дефолтом фильм 1987 года
с тремя раздачами при сериале 2015 года на тридцать.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.usecases.choice.asked_kind import asked_kind


def test_a_query_that_named_an_episode_narrows_the_menu_down_to_the_series() -> None:
    """Спросили серию - считаемся среди сериалов, а живая полнометражка не в счёт."""
    plans = [
        plan("Хорошая жена", 1987, seeders=3, asked_series=True),
        plan("Хорошая жена", 2015, seeders=18, kind="tv", asked_series=True),
    ]

    assert asked_kind(plans) == [2]


def test_a_query_that_named_no_episode_leaves_every_picture_in_the_running() -> None:
    """Серии не спрашивали - тип не назван, и гадать за человека нечего.

    «Мальтийский сокол» одинаково может оказаться и фильмом, и сериалом: сузь список
    молча - и дефолт выбирался бы по признаку, которого человек не называл.
    """
    plans = [plan("Мальтийский сокол", 1931), plan("Мальтийский сокол", 1941, kind="tv")]

    assert asked_kind(plans) == [1, 2]


def test_a_query_for_an_episode_without_a_single_series_counts_as_it_counted_before() -> None:
    """Сериалов в выдаче нет вовсе - гейт тут не судья тому, чего он не видел.

    Пустой ответ вместо картины был бы хуже неточного типа: цифре в скобках стало бы не
    на что указывать, а картина в каталоге при этом есть.
    """
    plans = [
        plan("Великий из бродячих псов", 2012, asked_series=True),
        plan("Великий из бродячих псов", 2016, asked_series=True),
    ]

    assert asked_kind(plans) == [1, 2]
