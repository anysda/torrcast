"""Зеркало :mod:`torrcast.usecases.choice.asked_season`: сезон, названный самим запросом.

Номер части у сериала и есть номер сезона: тем же прочтением запрос «имя N» становится
«имя sNe1». Значит картина, подписанная каталогом частью 2, первого сезона не несёт, и
дефолт спрошенного первого сезона ей не положен. Замер по сохранённым выдачам: «код гиас
s1e1» ставил дефолтом «Код Гиас: Восставший Лелуш 2» (2008) при живом первом сезоне в том
же меню.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.usecases.choice.asked_season import asked_season


def test_a_named_season_leaves_out_the_picture_the_catalogue_numbered_otherwise() -> None:
    """Спросили первый сезон - вторая часть франшизы дефолта не берёт."""
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", season=1, asked_series=True),
    ]

    assert asked_season(geass, [1, 2]) == [2]


def test_a_query_that_named_no_episode_lets_every_part_stay_in_the_running() -> None:
    """Серии не спрашивали - номер сезона не назван, и судить картины по нему нечем.

    Запрос «код гиас» - это просьба про франшизу целиком, и там дефолт решают живость и
    хронология, а не цифра в названии части.
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1),
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", season=1),
    ]

    assert asked_season(geass, [1, 2]) == [1, 2]


def test_a_menu_without_a_single_picture_of_the_asked_season_counts_as_it_counted() -> None:
    """Подходящих не осталось ни одной - считаем как считали.

    Спрошенного сезона в меню нет вовсе, и пустой ответ вместо картины был бы хуже
    неточного номера: цифре в скобках стало бы не на что указывать.
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш 2", 2008, kind="tv", part=2, season=1, asked_series=True),
        plan("Код Гиас: Восставший Лелуш 3", 2010, kind="tv", part=3, season=1, asked_series=True),
    ]

    assert asked_season(geass, [1, 2]) == [1, 2]
