"""Зеркало :mod:`torrcast.usecases.choice.certain_default`: граница молчаливого дефолта.

Спрашивают там, где о выборе есть честная строка. Молчат обе строки - значит другой
картины, которую человек мог иметь в виду, тут просто нет.
"""

from __future__ import annotations

from tests.usecases.choice.world import Outside, film, outside, parts, plan
from torrcast.usecases.choice.certain_default import certain_default


def test_a_franchise_that_starts_from_its_own_first_part_is_asked_about_nothing() -> None:
    """Первая часть жива и стоит сверху - спрашивать не о чем, о чём и говорит ответ."""
    cars = [
        plan("Тачки", 2006, part=1, seeders=66),
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    with outside(Outside()):
        assert certain_default(cars, "тачки") is True


def test_a_namesake_by_year_keeps_the_question() -> None:
    """Тёзка по году - самая тихая из подмен, и молчать про неё нельзя ни при каком дефолте."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))

    with outside(Outside()):
        assert certain_default(mummy, "мумия") is False


def test_a_default_that_would_swap_a_part_of_the_franchise_keeps_the_question() -> None:
    """Спрошенной части в выдаче нет - дефолт встал бы на другую, и это вопрос.

    Про смену картины тут молчат: сиквелы живы, стоят по хронологии, тёзок у них нет, -
    и сказать о верхе меню было бы нечего, если бы не имя запроса. А имя названо, первой
    части под ним не приехало, и другую часть за человека мы не включаем.
    """
    cars = [
        plan("Тачки 2", 2011, part=2, seeders=71),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    with outside(Outside()):
        assert certain_default(cars, "тачки") is False


def test_a_top_of_the_menu_the_lines_are_silent_about_keeps_the_question() -> None:
    """🔴 Верх меню и первая живая разошлись - молчание строк говорит не о верхе.

    Спросили серию: одноимённый фильм стоит первым пунктом, играть им нечего, и обе
    строки молчат - но молчат они про СЕРИАЛ. Взять молча верх значило бы взять то, о
    чём никто не высказался.
    """
    dead = film("Викинги 1958 BDRip 1080p", seeders=2)
    vikings = [
        plan("Викинги", 1958, pool=[dead], asked_series=True),
        plan("Викинги", 2013, kind="tv", seeders=90, asked_series=True),
    ]

    with outside(Outside()):
        assert certain_default(vikings, "викинги") is False
