"""Повод второго круга: выдача упёрлась в потолок индексера, а картины в ней нет."""

from __future__ import annotations

from tests.usecases.reinforce.stand import Indexer, franchise, pictures, row
from torrcast.usecases.reinforce.ceiling_hides_name import ceiling_hides_name

#: Выдача запроса «девять»: сотня строк про соседей по подстроке, самой картины нет.
_YARDS = [row("Девять ярдов / The Whole Nine Yards (2000) BDRip 1080p", "a")]
#: Та же выдача, но картина с именем запроса в ней есть - потолок обрезал только хвост.
_NINE = [*_YARDS, row("Девять / Nine (2009) BDRip 1080p", "b")]


def test_the_ceiling_hiding_the_asked_name_is_a_reason_to_ask_again() -> None:
    """🔴 TC-331. 21 раздача «Девяти» лежит за сотней строк, и каталог её не видит."""
    assert ceiling_hides_name(
        Indexer(capped=("RuTor",)), "девять", pictures(_YARDS), franchise("девять", _YARDS)
    )


def test_a_cut_tail_is_not_a_reason_while_the_name_is_in_the_pool() -> None:
    """Имя запроса в выдаче есть - обрезан хвост: досадно, но круга не стоит."""
    assert not ceiling_hides_name(
        Indexer(capped=("RuTor",)), "девять", pictures(_NINE), franchise("девять", _NINE)
    )


def test_nobody_hit_a_ceiling_means_nothing_is_hidden() -> None:
    """Потолка не было - за сотней ничего не лежит, и прятать картину нечему."""
    assert not ceiling_hides_name(
        Indexer(), "девять", pictures(_YARDS), franchise("девять", _YARDS)
    )


def test_an_empty_pool_is_answered_by_the_other_reinforcement() -> None:
    """Пустая выдача - пул тощий по определению, и там отвечает добор вторым языком."""
    assert not ceiling_hides_name(Indexer(capped=("RuTor",)), "девять", pictures(_YARDS), [])
