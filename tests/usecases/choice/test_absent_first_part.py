"""Зеркало :mod:`torrcast.usecases.choice.absent_first_part`: части нет в выдаче вовсе.

🔴 TC-830. Страж франшизы (:mod:`torrcast.usecases.choice.part_one_swap`) стерёг два
случая одним правилом, а они разные. Там, где спрошенная часть в выдаче ЕСТЬ, вопрос
осмыслен: её видно номером. Там, где её нет вовсе, вопрос сводился к «назови номер», а
нужного номера в списке не было - и ``cast тачки`` не начинал показ без человека.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, plan
from torrcast.usecases.choice.absent_first_part import absent_first_part

#: Первая часть, у которой в каталоге одни DVD-образы: рой есть, играть нечем.
VHS = film("Cars 2006 DVDRip XviD", seeders=100, codec="XviD", quality=None)


def test_a_first_part_missing_from_the_results_is_the_case_without_a_question() -> None:
    """«Тачек» в выдаче нет - выбирать между ними и «Тачками 2» не из чего."""
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert absent_first_part(cars, "тачки")


def test_a_dead_first_part_is_a_different_case_and_keeps_its_question() -> None:
    """Первая часть в выдаче ЕСТЬ, играть ей нечем - её называют номером, и вопрос остаётся.

    Решение владельца снимало вопрос ровно с ненайденной части. Подставлять другую вместо
    живой спрошенной по-прежнему запрещено, и расширять решение туда никто не давал права.
    """
    cars = [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    assert not absent_first_part(cars, "тачки")


def test_a_living_first_part_holds_the_default_and_asks_nothing() -> None:
    """Первая часть жива - дефолт стоит на ней, и стеречь тут нечего."""
    cars = [
        plan("Тачки", 2006, part=1, seeders=200),
        plan("Тачки 2", 2011, part=2, seeders=40),
    ]

    assert not absent_first_part(cars, "тачки")


def test_a_named_number_asked_for_that_very_part_and_got_it() -> None:
    """Номер назван явно - спрошенное отобрано до меню, и «ненайденной части» тут нет."""
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert not absent_first_part(cars, "тачки 2")


def test_a_request_about_another_franchise_finds_nothing_to_guard() -> None:
    """Запрос назвал не эту франшизу - молчание стража тут не про ненайденную часть."""
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert not absent_first_part(cars, "мумия")
