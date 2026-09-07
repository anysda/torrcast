"""Проверяет, какое имя годится источнику, знающему только латиницу."""

from __future__ import annotations

from torrcast.domain.said_in_latin import _said_in_latin


def test_a_latin_name_is_said_in_latin() -> None:
    """Имя латиницей - то самое, которым источник зовёт картину сам."""
    assert _said_in_latin("Bob's Burgers")
    assert _said_in_latin("Pohádky po babicce")


def test_a_russian_name_is_not() -> None:
    """Русское имя у латинского источника не совпадёт ни с чем."""
    assert not _said_in_latin("Укрытие")


def test_a_mixed_name_is_not_taken_for_a_latin_one() -> None:
    """Обе половины в одной строке - это не латинское имя, а строка с двумя именами."""
    assert not _said_in_latin("Брат / Brat")


def test_a_name_in_a_third_alphabet_is_not_latin_either() -> None:
    """Не кириллица - ещё не латиница: равенства с ответом источника не даст ни то, ни то."""
    assert not _said_in_latin("千と千尋の神隠し")
    assert not _said_in_latin("")
