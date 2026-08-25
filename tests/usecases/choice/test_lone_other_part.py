"""Зеркало :mod:`torrcast.usecases.choice.lone_other_part`: отказ вместо чужой части.

🔴 TC-814. Меню при одной картине не задаётся вовсе, и страж перескока туда не доходил:
`cast лёд` молча включал «Лёд 3» 2024 года. Просили одну часть - другую не подставляем.
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.usecases.choice.lone_other_part import lone_other_part


def test_the_only_picture_found_being_another_part_is_refused_by_name_and_number() -> None:
    """Нашлась одна картина, и она - третья часть: строка называет её и запрос к ней."""
    ice = [plan("Лёд 3", 2024, part=3, seeders=3)]

    assert lone_other_part(ice, "лёд") == (
        "«лёд»: первой части в выдаче нет, и другую часть сам не включаю - "
        "есть «Лёд 3 (2024)», спроси её номером «лёд 3»"
    )


def test_an_original_name_asks_about_the_same_franchise_as_the_russian_one() -> None:
    """Запрос «cars» читается так же, как «тачки»: франшиза сверяется в двух языках."""
    cars = [plan("Тачки 2", 2011, part=2, original="Cars 2", seeders=40)]

    assert lone_other_part(cars, "cars").startswith("«cars»: первой части в выдаче нет")


def test_a_number_named_by_the_person_asks_for_exactly_what_was_found() -> None:
    """Номер назван явно - спрошенное и нашлось, подменять нечего."""
    assert lone_other_part([plan("Лёд 3", 2024, part=3, seeders=3)], "лёд 3") == ""


def test_the_first_part_alone_is_the_answer_to_the_query() -> None:
    """Нашлась сама первая часть - это и есть спрошенное."""
    assert lone_other_part([plan("Тачки", 2006, part=1, seeders=66)], "тачки") == ""


def test_a_picture_outside_any_numbered_line_has_no_part_to_substitute() -> None:
    """Картина без номера части («Оппенгеймер») подменять было нечем."""
    assert lone_other_part([plan("Оппенгеймер", 2023, seeders=300)], "oppenheimer") == ""


def test_a_stranger_franchise_is_none_of_the_query_business() -> None:
    """Имя запроса зовёт чужую линейку - до найденной картины оно не относится."""
    assert lone_other_part([plan("Тачки 2", 2011, part=2, seeders=40)], "мумия") == ""


def test_a_numbered_book_series_is_not_a_franchise_of_pictures() -> None:
    """Номерованная книжная серия картиной не является - её тут не считают вовсе."""
    ludens = [plan("Homo Ludens 2", 2019, kind="other", part=2, seeders=5)]

    assert lone_other_part(ludens, "homo ludens") == ""


def test_a_menu_of_several_pictures_belongs_to_the_guard_of_the_jump() -> None:
    """Картин несколько - там свой страж, а тут молчание."""
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert lone_other_part(cars, "тачки") == ""
