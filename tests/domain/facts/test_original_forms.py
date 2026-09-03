"""Проверяет формы оригинального имени: номер части арабской цифрой и римской."""

from __future__ import annotations

from torrcast.domain.facts.original_forms import original_forms


def test_the_roman_form_is_added_and_never_replaces_the_arabic_one() -> None:
    """🔴 ОТРИЦАТЕЛЬНАЯ ПРОБА: замени форму вместо добавления - и «Mad Max 2» пропал.

    Раздел держит римскую цифру у «Poltergeist II: The Other Side» и арабскую у
    «Mad Max 2», «Ocean's 11» и «Final Destination 5». Угадать сторону нечем, поэтому
    спрашиваются обе - в одном и том же запросе, а не в двух походах.
    """
    assert original_forms("Poltergeist 2: The Other Side") == [
        "Poltergeist 2: The Other Side",
        "Poltergeist II: The Other Side",
    ], "арабская форма потерялась, а под ней лежит «Mad Max 2»"


def test_a_name_without_a_part_number_stays_one_single_name() -> None:
    """Второе имя тут было бы вторым промахом: лишнее имя удлиняет строку запроса."""
    assert original_forms("The Matrix") == ["The Matrix"]
    assert original_forms("Ocean's 11") == ["Ocean's 11"], "двузначный номер не часть"


def test_a_digit_inside_a_word_or_a_year_is_left_alone() -> None:
    """🔴 Цифра внутри слова и год - не номер части: «Se7en» и «2012» неприкосновенны.

    А вот «District 9» вторую форму получает, и это осознанно: отличить одиноким
    взглядом номер части от числа в имени нечем, а лишнее имя тут стоит ноль - оно
    едет в том же ``titles``, что и первое, и раздел отвечает на него пустотой.
    """
    assert original_forms("Se7en") == ["Se7en"], "цифра внутри слова не номер части"
    assert original_forms("2012") == ["2012"], "год не номер части"
    assert original_forms("District 9") == ["District 9", "District IX"]


def test_an_empty_original_is_not_a_name_to_ask_about() -> None:
    """Оригинала у находки бывает нет вовсе, и спрашивать про пустую строку нечего."""
    assert original_forms("") == []
    assert original_forms("   ") == []
