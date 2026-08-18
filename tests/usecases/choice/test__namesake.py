"""Зеркало :mod:`torrcast.usecases.choice._namesake`: тёзка по имени и году.

Одноимённые части - самая тихая из подмен: в меню они отличаются одним годом в скобках.
Признак решает, скажут ли человеку об этом вслух, - и обе стороны выбора обязаны его
проходить одинаково.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts, plan
from torrcast.usecases.choice import _namesake


def test_the_same_title_under_a_different_year_is_a_namesake() -> None:
    """То же название, другой год - это ДРУГАЯ картина, и молчать о ней нельзя.

    Человек, назвавший «мумия», получает «Мумию» - вопрос лишь, которую из трёх.
    """
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    assert _namesake(mummy, 2, 1) is True
    assert _namesake(mummy, 1, 2) is True, "признак симметричен: говорят обе стороны выбора"


def test_the_same_title_in_the_same_year_is_not_a_namesake_but_the_same_picture() -> None:
    """Совпал и год - развести картины нечем, и говорить о подмене не о чем.

    Сочти такую пару тёзками - и меню объявляло бы подменой выбор картины самой собой.
    """
    twins = parts(("Девять", 2009, 40), ("Девять", 2009, 12))

    assert _namesake(twins, 2, 1) is False


def test_a_neighbour_of_the_franchise_is_not_a_namesake_at_all() -> None:
    """«Тачки 2» рядом с «Тачками» - не тёзка, а другое кино той же франшизы.

    Считай их тёзками - и строка про подмену печаталась бы на каждой второй франшизе,
    то есть перестала бы читаться там, где она про дело.
    """
    cars = parts(("Тачки", 2006, 66), ("Тачки 2", 2011, 40))

    assert _namesake(cars, 2, 1) is False


def test_the_case_of_the_letters_does_not_make_two_pictures_different() -> None:
    """Регистр букв каталог пишет как придётся, и тёзку он скрывать не вправе."""
    pair = [plan("НЕЛЮБОВЬ", 2017), plan("Нелюбовь", 2022)]

    assert _namesake(pair, 2, 1) is True
