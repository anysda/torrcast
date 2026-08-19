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


def test_a_menu_where_everyone_has_a_single_release_stays_exactly_as_it_was() -> None:
    """Живых с очередью нет вовсе - список остаётся как был.

    Иначе ступень молчаливо превращала бы «живую» картину в мёртвую, а выбирать всё
    равно не из чего.
    """
    lonely = [plan("Кино", 1999, seeders=16), plan("Кино", 2001, seeders=28)]

    assert backed(lonely, [1, 2]) == [1, 2]
