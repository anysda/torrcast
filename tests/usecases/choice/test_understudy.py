"""Зеркало :mod:`torrcast.usecases.choice.understudy`: дублёр выбранной картины.

🔴 TC-203. У выбранной картины кончились все раздачи, а рядом в меню стоит одноимённая
живая - и человек читал отказ. Замер каталога: 6 отказов из 115, и самый наглядный -
«Человек-невидимка», где дефолт садился на 1933 год при живой картине 2020 года.
"""

from __future__ import annotations

from tests.usecases.choice.world import parts, plan
from torrcast.usecases.choice.understudy import understudy


def test_a_live_namesake_is_the_one_that_finishes_the_evening_instead() -> None:
    """Тёзка - та же вещь, снятая дважды: имя человек назвал верно, промахнулись годом.

    Отказ там был честен про картину и неправдой про вечер: кино с этим именем в
    каталоге есть, и оно играет.
    """
    invisible = parts(("Человек-невидимка", 1933, 12), ("Человек-невидимка", 2020, 140))

    spare = understudy(invisible, invisible[0])

    assert spare is not None and spare.picture.year == 2020


def test_a_neighbour_of_the_franchise_is_never_taken_as_an_understudy() -> None:
    """🔴 «Тачки 2» вместо «Тачек» - это другое кино, и уходить туда самому нельзя.

    Про таких соседей говорит подсказка отказа, и она остаётся подсказкой: разница между
    тёзкой и соседкой по франшизе тут принципиальная, а не оттеночная.
    """
    cars = parts(("Тачки", 2006, 66), ("Тачки 3", 2017, 121))

    assert understudy(cars, cars[0]) is None


def test_a_series_never_stands_in_for_a_film_of_the_same_name() -> None:
    """Тип обязан совпасть: полнометражка и одноимённый сериал - разные вещи.

    Подменять одно другим молча нельзя ровно по той же причине, по какой этого не
    делает дефолт (TC-192).
    """
    unloved = [plan("Нелюбовь", 2017, seeders=9), plan("Нелюбовь", 2022, kind="tv", seeders=120)]

    assert understudy(unloved, unloved[0]) is None


def test_a_dead_namesake_is_no_understudy_and_the_refusal_stays_the_refusal() -> None:
    """Тёзка мертва - уходить некуда: живость дублёра меряется тем же порогом."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 2))

    assert understudy(mummy, mummy[0]) is None


def test_a_menu_of_one_picture_has_nobody_to_stand_in() -> None:
    """Меню из одной картины - тёзок нет по построению."""
    single = parts(("Человек-невидимка", 1933, 12))

    assert understudy(single, single[0]) is None


def test_of_several_namesakes_the_liveliest_one_is_taken_and_the_circle_ends_there() -> None:
    """Круг ровно один: берём самую живую из тёзок и дальше не перебираем.

    Лишний заход стоит человеку секунд, а цель пути - десять секунд до картинки.
    """
    mummy = parts(("Мумия", 1999, 8), ("Мумия", 2017, 58), ("Мумия", 2026, 300))

    spare = understudy(mummy, mummy[0])

    assert spare is not None and spare.picture.year == 2026


def test_a_plan_that_is_not_in_the_menu_at_all_gets_no_understudy() -> None:
    """Картины нет в списке - искать ей тёзку не по чему, и это не догадка."""
    mummy = parts(("Мумия", 1999, 47), ("Мумия", 2017, 58))
    stranger = plan("Дюна", 2021, seeders=90)

    assert understudy(mummy, stranger) is None
