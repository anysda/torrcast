"""Зеркало :mod:`torrcast.usecases.choice.part_one_swap`: честная строка вместо дефолта.

🔴 TC-373. Запрос «тачки» - это просьба про «Тачки» 2006 года, и пока первая часть
играет, дефолт стоит на ней. А когда её нет в выдаче или играть ей нечем, дефолт по
правилу «первая живая часть» перескакивал на «Тачки 2» - и Enter включал другое кино той
же франшизы, которого не просили.
"""

from __future__ import annotations

from tests.usecases.choice.world import film, parts, plan
from torrcast.usecases.choice import part_one_swap

#: Первая часть, у которой в каталоге одни DVD-образы: рой есть, играть нечем.
VHS = film("Cars 2006 DVDRip XviD", seeders=100, codec="XviD", quality=None)


def test_a_dead_first_part_stops_the_default_and_the_number_is_named_by_the_person() -> None:
    """Дефолта нет вовсе: строка называет, что с первой частью, а номер зовёт человек.

    Строка про подмену была и раньше, но показ всё равно начинался сам - и Enter включал
    «Тачки 2» вместо просимых «Тачек».
    """
    cars = [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
        plan("Тачки 3", 2017, part=3, seeders=121),
    ]

    assert part_one_swap(cars, "тачки") == (
        "«Тачки (2006)» не играет: играть у неё нечем - ни одной годной раздачи; "
        "вместо неё другую часть сам не включаю - вот что есть, назови номер"
    )


def test_a_first_part_missing_from_the_results_gets_its_own_honest_line() -> None:
    """Первой части в выдаче нет вовсе - причины у неё нет, а строка обязана быть.

    Молчание тут значило бы, что Enter включит вторую часть, ни словом об этом не
    сказав: то же самое кино не в тот вечер.
    """
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert part_one_swap(cars, "тачки") == (
        "«тачки»: первой части в выдаче нет, и вместо неё другую часть сам не включаю - "
        "вот что есть, назови номер"
    )


def test_an_original_name_asks_about_the_same_franchise_as_the_russian_one() -> None:
    """Запрос «cars» читается так же, как «тачки»: имя первой части сверяется в двух языках.

    Иначе ограждение отключалось бы одной сменой раскладки, а подмена части оставалась.
    """
    cars = [
        plan("Тачки", 2006, part=1, original="Cars", pool=[VHS]),
        plan("Тачки 2", 2011, part=2, original="Cars 2", seeders=40),
    ]

    assert part_one_swap(cars, "cars").startswith("«Тачки (2006)» не играет")


def test_a_part_named_by_its_number_was_already_picked_and_the_default_is_honest() -> None:
    """Номер назван явно («тачки 2») - спрошенное уже отобрано до меню.

    Дефолт тут ровно оно, и отнимать его значило бы спрашивать человека о том, что он
    уже сказал.
    """
    cars = [
        plan("Тачки", 2006, part=1, pool=[VHS]),
        plan("Тачки 2", 2011, part=2, seeders=40),
    ]

    assert part_one_swap(cars, "тачки 2") == ""


def test_a_franchise_without_numbered_parts_keeps_the_rule_first_live_picture() -> None:
    """«Моана», «Мумия» - линейки по номерам нет, и первая ЖИВАЯ картина и есть ответ.

    Решение «дефолт франшизы - первая живая часть» тут не тронуто: подменять нечего.
    """
    mummy = parts(("Мумия", 1999, 0), ("Мумия", 2017, 58))

    assert part_one_swap(mummy, "мумия") == ""


def test_a_default_that_sat_down_on_the_first_part_itself_needs_no_line() -> None:
    """Первая часть играет - дефолт честен, и говорить не о чем."""
    cars = [plan("Тачки", 2006, part=1, seeders=66), plan("Тачки 2", 2011, part=2, seeders=40)]

    assert part_one_swap(cars, "тачки") == ""


def test_a_namesake_of_the_first_part_by_year_keeps_the_old_leniency() -> None:
    """«Человек-невидимка» 2020 вместо 1933 - та же вещь под тем же именем.

    Послабление тёзке остаётся: имя человек назвал верно, промахнулись мы годом, и
    отбирать у него дефолт незачем.
    """
    invisible = [
        plan("Человек-невидимка", 1933, part=1, pool=[VHS]),
        plan("Человек-невидимка", 2020, part=2, seeders=140),
    ]

    assert part_one_swap(invisible, "человек-невидимка") == ""


def test_a_numbered_book_series_next_to_a_film_is_no_franchise_of_its_own() -> None:
    """Линейкой считаются только картины, и «первая часть» младше соседа - не первая.

    «Homo Ludens 1» рядом со «Сталкером» франшизы не образует: перед нами семья
    однофамильцев, и там дефолт честен.
    """
    family = [plan("Сталкер", 1979, seeders=80), plan("Homo Ludens 1", 2010, part=1, seeders=90)]

    assert part_one_swap(family, "сталкер") == ""


def test_a_query_that_named_a_picture_rather_than_a_franchise_changes_nothing() -> None:
    """Запрос назвал не франшизу - подменять тут нечего, и строки нет."""
    cars = [plan("Тачки", 2006, part=1, pool=[VHS]), plan("Тачки 2", 2011, part=2, seeders=40)]

    assert part_one_swap(cars, "мумия") == ""


def test_a_menu_of_one_picture_was_never_a_choice_between_parts() -> None:
    """Картина одна - меню не задавалось вовсе, и подменять было нечего."""
    assert part_one_swap([plan("Тачки", 2006, part=1, pool=[VHS])], "тачки") == ""
