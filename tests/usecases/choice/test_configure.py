"""Зеркало :mod:`torrcast.usecases.choice.configure`: слот внешнего мира меню.

Правила соседних сценариев и ввод-вывод пульта сценарий выбора не импортирует, а
получает от композиционного корня. Слот тут не украшение архитектуры: спрашивается он на
КАЖДОМ обращении, и потому подмена внешнего мира на стенде остаётся той же силы, что и
боевая раскладка.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts
from torrcast.usecases.choice import alive_numbers
from torrcast.usecases.choice.configure import _environment_port


def test_the_slot_gives_back_exactly_the_world_that_was_put_into_it() -> None:
    """Что положили, то и спрашивается: своего мнения о внешнем мире слот не имеет."""
    world = Outside()

    with outside(world):
        assert _environment_port() is world


def test_the_units_ask_the_slot_at_every_call_and_not_once_at_import() -> None:
    """Порог живости спрашивается у слота в момент вопроса, а не запоминается импортом.

    Запомни единица боевое число на импорте - и стенд мерил бы боевую раскладку, молча
    выдавая её за подставленную: зелёный прогон без единого измерения.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with outside(Outside(alive_seeders=50)):
        assert alive_numbers(mummy, [1, 2]) == [2], "порог 50 отсекает картину на 47 сидах"
    with outside(Outside(alive_seeders=5)):
        assert alive_numbers(mummy, [1, 2]) == [1, 2], "тот же список при пороге 5"


def test_a_second_call_replaces_the_world_instead_of_adding_to_it() -> None:
    """Слот один: новая раскладка вытесняет прежнюю целиком, а не ложится поверх."""
    first, second = Outside(), Outside()

    with outside(first), outside(second):
        assert _environment_port() is second
