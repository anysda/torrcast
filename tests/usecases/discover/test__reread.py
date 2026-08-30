"""Зеркало второго захода по той же строке: забытая раскладка и цифра в названии.

Оба захода стоят ровно один круг к индексерам и зовутся ТОЛЬКО там, где иначе человек
уже читал бы отказ. Мера про это и про их вежливость: не помогло - выдача остаётся
прежней, а не расширенной, иначе сдвинулась бы нумерация франшизы.
"""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row
from torrcast.usecases.discover._reread import _relayout


@pytest.fixture(autouse=True)
def _russian_ladder(_russian_product: None) -> None:
    """Предмет модуля - русская строка о забытой раскладке и её номере."""


CARS = "Тачки / Cars (2006) BDRip 1080p"


def test_a_latin_query_is_read_as_the_forgotten_keyboard_layout() -> None:
    """`cast nfxrb` - это «тачки»: отказ по такой строке правдив только для строки."""
    client = Indexer([row(CARS)])
    said = Said()

    query, name, index, raw = _relayout(client, "nfxrb", "nfxrb", None, said)

    assert (query, name, index) == ("тачки", "тачки", None)
    assert len(raw) == 1
    assert said.notes == ["«nfxrb» - это «тачки» в русской раскладке"]


def test_the_part_number_is_read_again_in_the_swapped_query() -> None:
    """«nfxrb 2» - это «тачки 2»: цифра обязана снова стать номером, а не именем."""
    client = Indexer([row("Тачки 2 / Cars 2 (2011) BDRip 1080p")])

    query, name, index, _raw = _relayout(client, "nfxrb 2", "nfxrb 2", None, Said())

    assert (query, name, index) == ("тачки 2", "тачки", 2)


def test_a_query_that_is_already_russian_is_left_alone() -> None:
    """Двойника у кириллической строки нет - заход не тратится вовсе."""
    client = Indexer([row(CARS)])

    assert _relayout(client, "тачки", "тачки", None, Said()) == ("тачки", "тачки", None, [])
    assert client.asked == [], "лишнего круга к индексерам тут не бывает"


def test_a_swapped_query_that_found_nothing_changes_nothing() -> None:
    """Перевод не помог - остаётся ПРЕЖНЯЯ строка: молчаливой подмены не бывает."""
    said = Said()

    found = _relayout(Indexer([]), "nfxrb", "nfxrb", 1, said)

    assert found == ("nfxrb", "nfxrb", 1, [])
    assert said.notes == []
