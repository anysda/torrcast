"""Зеркало :mod:`torrcast.usecases.choice.backed`: за кем стоит очередь раздач.

Сиды в выдаче - это обещание индексера, а не факт: раздача, которая не отдаёт ни
метаданных, ни потока, числится в выдаче ровно так же бодро. За картиной с очередью
стоит дюжина таких обещаний, за однораздачной - одно, и осечка на нём кончает вечер.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, plan
from torrcast.usecases.choice.backed import _rival, backed


def test_a_lone_release_yields_to_a_queue_that_is_livelier_than_it() -> None:
    """Замер «Мальтийского сокола»: 1931 год одной раздачей на 16 сид уступает 1941-му.

    У картины 1941 года двадцать две раздачи, и лучшая ГОДНАЯ держит 28: доля честная,
    порог живости однораздачная тёзка проходит - и дефолт садился на неё.
    """
    falcon = [
        plan("Мальтийский сокол", 1931, seeders=16),
        plan(
            "Мальтийский сокол",
            1941,
            pool=[film("верх очереди", seeders=5), film("годный сосед", seeders=28)],
        ),
    ]

    assert backed(falcon, [1, 2]) == [2]


def test_a_lone_release_that_is_itself_the_liveliest_thing_around_keeps_its_place() -> None:
    """Однораздачная уступает не всякой очереди, а только той, которая её же и живее.

    Ранжировать картины числом раздач эта ступень НЕ начинает: на том уже обжигались -
    до-вожак по числу раздач выдавал сиквел вместо основной картины.
    """
    franchise = [
        plan("Первая часть", 2006, seeders=100),
        plan("Вторая часть", 2011, pool=[film("a", seeders=90), film("b", seeders=80)]),
    ]

    assert backed(franchise, [1, 2]) == [1, 2]


def test_the_depth_of_a_series_queue_says_nothing_about_a_film_of_the_same_name() -> None:
    """🔴 TC-192. Уступают друг другу картины ОДНОГО типа, и это ограждение.

    У сериала раздача на каждый сезон, у фильма она одна на всё кино, и мерить их одной
    линейкой значит объявлять фильм «формально живым» за то, что он фильм. Замер:
    «Нелюбовь» Звягинцева одной раздачей на 40 сид против сериала «НЕлюбовь [S01]» двумя
    раздачами на 120, и дефолтом молча вставал сериал.
    """
    unloved = [
        plan("Нелюбовь", 2017, seeders=40),
        plan(
            "НЕлюбовь",
            2022,
            kind="tv",
            pool=[film("s01", seeders=120), film("s02", seeders=60)],
        ),
    ]

    assert backed(unloved, [1, 2]) == [1, 2]
    assert _rival(unloved, [2], 1) == 0, "очередей своего типа нет - уступать нечему"


def test_a_named_episode_makes_a_franchise_neighbour_no_rival_at_all() -> None:
    """🔴 TC-818. Зритель назвал серию - уступают друг другу ТЁЗКИ, а не соседки.

    Глубина очереди говорит о том, чем играет она сама, а у соседки по франшизе это
    другой сериал со своим первым сезоном. Замер: «код гиас s1e1» - «Код Гиас:
    Восставший Лелуш» одной раздачей на 11 сид уступал дефолт сериалу «Code Geass:
    Dakkan no Rozé» (19 раздач, лучшая на 77), которого не спрашивали.
    """
    geass = [
        plan("Код Гиас: Восставший Лелуш", 2006, kind="tv", seeders=11, asked_series=True),
        plan(
            "Code Geass: Dakkan no Rozé",
            2024,
            kind="tv",
            asked_series=True,
            pool=[film("e01", seeders=77), film("e02", seeders=13)],
        ),
    ]

    assert backed(geass, [1, 2]) == [1, 2]
    assert _rival(geass, [2], 1) == 0, "соседка по франшизе - не тёзка, уступать нечему"


def test_a_franchise_neighbour_stays_a_rival_where_no_episode_was_named() -> None:
    """Серию запрос не называл - ограждение молчит, речь про франшизу целиком.

    «Замок Калиостро» с десятью раздачами законно перебивает однораздачного тёзку
    «Rupan sansei» 2014 года на три сида: спрошена франшиза, а не серия сериала.
    """
    lupin = [
        plan("Rupan sansei", 2014, seeders=3),
        plan(
            "Замок Калиостро",
            1979,
            pool=[film("верх", seeders=10), film("сосед", seeders=8)],
        ),
    ]

    assert backed(lupin, [1, 2]) == [2]


def test_a_menu_where_everyone_has_a_single_release_stays_exactly_as_it_was() -> None:
    """Живых с очередью нет вовсе - список остаётся как был.

    Иначе ступень молчаливо превращала бы «живую» картину в мёртвую, а выбирать всё
    равно не из чего.
    """
    lonely = [plan("Кино", 1999, seeders=16), plan("Кино", 2001, seeders=28)]

    assert backed(lonely, [1, 2]) == [1, 2]


def test_a_season_split_off_by_the_catalogue_yields_to_its_own_series() -> None:
    """Номер части у сериала - это сезон, и «Ход королевы 1» с «Ход королевы» один сериал.

    Замер по сохранённым выдачам: «ход королевы s1e7» - каталог отделяет сезон в свою
    картину на одну раздачу, и она вставала дефолтом при собственном сериале с сорока
    тремя. Сравнение по целой подписи разводило их в чужаков, а уступать чужаку нечему.
    """
    gambit = [
        plan("Ход королевы 1", 2020, kind="tv", part=1, seeders=9, asked_series=True),
        plan(
            "Ход королевы",
            2020,
            kind="tv",
            asked_series=True,
            pool=[film("e07", seeders=60), film("e06", seeders=44)],
        ),
    ]

    assert backed(gambit, [1, 2]) == [2]
    assert _rival(gambit, [2], 1) == 60, "сезон и его же сериал - тёзки, номер части не в счёт"
