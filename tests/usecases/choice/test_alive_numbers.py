"""Зеркало :mod:`torrcast.usecases.choice.alive_numbers`: у кого есть чем играть.

Порог - СВОЙ рой картины, а не доля от самой живой части франшизы. Доля тут была прямой
ошибкой и стоила классики: одна свежая часть с большим роем объявляла мёртвой всю
остальную франшизу.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts
from torrcast.domain.rank_settings import ALIVE_SEEDERS
from torrcast.usecases.choice import alive_numbers


def test_a_picture_is_alive_by_its_own_swarm_and_not_by_a_share_of_the_liveliest() -> None:
    """Живость - свой рой картины; сотни сидов у соседа её ни отменить, ни подтвердить.

    Замер «мумии»: свежая часть 2026 года набирает сотни сидов, а «Мумия» 1999 года при
    живых десятках не дотягивала до четверти от неё и пропускалась - дефолтом десять
    прогонов из десяти вставала картина, которой человек не называл.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert alive_numbers(mummy, [1, 2, 3]) == [1, 2, 3]


def test_the_threshold_is_inclusive_and_a_picture_exactly_on_it_is_still_alive() -> None:
    """Ровно на пороге картина ещё живая, а на знак ниже - уже нет.

    Число одно на весь инструмент: сделай сравнение строгим - и картина ровно на пороге
    пропадала бы из дефолта у одной мерки и оставалась бы у другой.
    """
    edge = parts(("Кино", 1999, ALIVE_SEEDERS), ("Кино", 2001, ALIVE_SEEDERS - 1))

    assert alive_numbers(edge, [1, 2]) == [1]


def test_only_the_numbers_asked_about_are_answered_about() -> None:
    """Спросили про часть меню - отвечаем про неё: остальные картины не в счёт.

    Через этот же список приезжает тип, названный запросом: подмешай сюда картины, о
    которых не спрашивали, - и дефолт сериала считался бы среди полнометражек.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    assert alive_numbers(mummy, [2, 3]) == [2, 3]


def test_a_menu_without_a_single_live_picture_answers_with_an_empty_list() -> None:
    """Живых нет вовсе - пустой ответ, а не тихая подстановка кого-нибудь."""
    dead = parts(("Кино", 1999, 1), ("Кино", 2001, 0))

    assert alive_numbers(dead, [1, 2]) == []
