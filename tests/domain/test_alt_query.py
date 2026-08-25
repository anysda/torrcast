"""Зеркало :mod:`torrcast.domain.alt_query`: вторым заходом ищем картину другим именем."""

from torrcast.domain.alt_query import alt_query
from torrcast.domain.release import Release


def _found(title: str, original: str) -> Release:
    return Release(raw_name=f"{title} / {original}", title=title, original=original)


def test_the_latin_name_found_among_releases_becomes_the_second_query() -> None:
    """Русский запрос добирается латиницей: её приносит оригинал найденной раздачи."""
    assert alt_query("Брат", [_found("Брат", "Brother")]) == "Brother"


def test_a_name_already_known_beats_the_search_through_releases() -> None:
    """Знакомое имя не надо выуживать из выдачи: справка уже назвала его."""
    assert alt_query("Брат", [], known="Brother") == "Brother"


def test_a_latin_query_goes_back_for_the_native_name() -> None:
    """Заход зеркальный: латинский запрос добирается русским названием."""
    assert alt_query("Brother", [], native="Брат") == "Брат"


def test_a_second_name_equal_to_the_first_is_not_a_second_query() -> None:
    """Тот же слаг другой выдачи не даст: повторный заход был бы холостым."""
    assert alt_query("Brother", [], known="brother") == ""


def test_a_one_word_query_without_any_answer_is_taken_in_latin_letters() -> None:
    """Одно слово кириллицей - последняя попытка: трекеры пишут его латиницей."""
    assert alt_query("Брат", []) == "brat"


def test_a_long_query_with_nothing_found_gets_no_second_name() -> None:
    """Многословный запрос вслепую транслитерировать нечего: имя так не пишут."""
    assert alt_query("Заброшенный дом", []) == ""
