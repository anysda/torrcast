"""Зеркало :mod:`torrcast.usecases.choice.namesake_take`: самая живая тёзка дефолта.

🔴 TC-812, решение владельца 26-08-2026: тёзки по году - разные картины под одним
именем - больше не спрашивают: берётся самая живая, и берётся не молча. Франшизу это
не трогает: дефолт номерованных частей - по-прежнему первая живая часть.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, outside, parts, plan
from torrcast.usecases.choice.enter_take import enter_take
from torrcast.usecases.choice.namesake_take import namesake_take


def test_the_liveliest_namesake_is_taken() -> None:
    """«мумия»: первая живая по хронологии - 1999 год, а живее всех тёзка 2017 года."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert namesake_take(mummy) == 2


def test_the_default_itself_is_taken_when_it_is_the_liveliest() -> None:
    """«титаник»: живее всех сам дефолт - взятие перестало быть вопросом, не сменившись."""
    titanic = parts(("Титаник", 1943, 1), ("Титаник", 1953, 2), ("Титаник", 1997, 165))

    with outside(Outside()):
        assert namesake_take(titanic) == 3


def test_a_dead_namesake_is_not_taken_however_early_it_stands() -> None:
    """Мёртвая тёзка весит свой рой, и живой соседке она не конкурент."""
    mummy = parts(("Мумия", 1932, 2), ("Мумия", 1999, 47))

    with outside(Outside()):
        assert namesake_take(mummy) == 2


def test_without_namesakes_there_is_no_take() -> None:
    """Разные названия - не тёзки: у частей франшизы своё правило, у соседей - свой страж."""
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    with outside(Outside()):
        assert namesake_take(cars) == 0


def test_a_differently_named_livelier_neighbour_is_not_taken() -> None:
    """Живее всех в меню - картина с ДРУГИМ именем: она в круг взятия не входит вовсе."""
    menu = parts(("Моана", 2016, 40), ("Моана 2", 2024, 222))

    with outside(Outside()):
        assert namesake_take(menu) == 0


def test_a_single_picture_has_no_namesakes() -> None:
    """Картина одна - тёзок нет, и вопроса о круге взятия нет."""
    with outside(Outside()):
        assert namesake_take(parts(("Мумия", 1999, 47))) == 0


def test_namesakes_of_the_other_kind_are_out_of_the_take() -> None:
    """Спросили серию - одноимённая полнометражка не «вариант поживее», а другое кино."""
    vikings = [
        plan("Викинги", 1958, seeders=300, asked_series=True),
        plan("Викинги", 2013, kind="tv", seeders=90, asked_series=True),
    ]

    with outside(Outside()):
        assert namesake_take(vikings) == 0, "тёзки считаются внутри названного типа"


def test_the_namesake_of_the_year_named_is_taken() -> None:
    """TC-1398: «Призрак в доспехах 2026» - год назван, и живой фильм 1995 года не подмена ему."""
    ghost = [
        plan("Призрак в доспехах", 1995, seeders=300),
        plan("Призрак в доспехах", 2026, kind="tv", seeders=60),
    ]

    with outside(Outside()):
        assert namesake_take(ghost) == 1
        assert namesake_take(ghost, "Призрак в доспехах 2026") == 2
        assert namesake_take(ghost, "Призрак в доспехах 2031") == 1


def test_enter_takes_the_namesake_of_the_year_named() -> None:
    """Enter спрашивает взятие тёзки тем же запросом: «Мумия 2017» не уезжает в 1999 год."""
    mummy = parts(("Мумия", 1999, 300), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert enter_take(mummy, "Мумия").number == 1
        assert enter_take(mummy, "Мумия 2017").number == 2


def test_a_dead_namesake_of_the_year_named_leaves_the_liveliest() -> None:
    """Год назван, но играть картине этого года нечем: берётся самая живая, как прежде."""
    ghost = [
        plan("Призрак в доспехах", 1995, seeders=300),
        plan("Призрак в доспехах", 2026, kind="tv", seeders=1),
    ]

    with outside(Outside()):
        assert namesake_take(ghost, "Призрак в доспехах 2026") == 1
