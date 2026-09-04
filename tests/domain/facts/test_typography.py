"""Зеркало :mod:`torrcast.domain.facts.typography`."""

from __future__ import annotations

from torrcast.domain.facts.typography import typography


def test_straight_quotes_become_the_ones_the_section_writes() -> None:
    """Раздача пишет прямыми кавычками, статья лежит под ёлочками."""
    assert typography('Анатомия "Тату"') == ["Анатомия «Тату»"]


def test_a_colon_before_the_subtitle_also_gets_asked_as_a_period() -> None:
    """Разделитель подписи у раздачи двоеточие, у раздела точка."""
    assert typography('Рерберг и Тарковский: Обратная сторона "Сталкера"') == [
        "Рерберг и Тарковский: Обратная сторона «Сталкера»",
        "Рерберг и Тарковский. Обратная сторона «Сталкера»",
    ]


def test_the_colon_form_is_not_replaced_but_joined() -> None:
    """У франшизы двоеточие своё: «Дюна: Часть вторая» так и называется."""
    assert typography("Дюна: Часть вторая")[0] == "Дюна: Часть вторая"


def test_an_apostrophe_inside_a_word_is_not_a_quotation_mark() -> None:
    """Одиночный знак бывает апострофом, и пары ему нет."""
    assert typography("Rock'n'Roll") == ["Rock'n'Roll"]


def test_a_colon_without_a_space_is_not_a_subtitle_separator() -> None:
    """Двоеточие бывает временем или счётом, а не разделителем подписи."""
    assert typography("Матч 3:0") == ["Матч 3:0"]


def test_a_nameless_ask_asks_for_nothing() -> None:
    """Пустое имя не даёт ни одной формы: спрашивать нечего."""
    assert typography("   ") == []
