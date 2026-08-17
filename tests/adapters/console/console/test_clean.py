"""Чистка ответа: битый ввод не доезжает до парсера и переживает запись в файл."""

from __future__ import annotations

from torrcast.adapters.console.console.clean import clean


def test_broken_input_never_reaches_the_parser() -> None:
    """Одиночные суррогаты и управляющие символы чистятся на любом ответе.

    Половинки русских букв приезжают из pty без ``IUTF8``; такую строку нельзя ни
    записать в состояние, ни отправить в поиск - она рвётся на ``encode``.
    """
    assert clean("моа\udcd0на") == "моана"
    assert clean(" да\x07\x1b ") == "да"
    # Ответ из битого pty обязан пережить запись в файл - на этом рвалось всё остальное.
    assert clean("Моана\udce2\udc80").encode("utf-8", "strict")


def test_a_tab_survives_but_the_edges_do_not() -> None:
    """Табуляция - обычный пробельный символ ответа, а края обрезаются."""
    assert clean("  моана 2  ") == "моана 2"
    assert clean("моана\tдва") == "моана\tдва"


def test_the_answer_comes_back_in_one_normal_form() -> None:
    """NFC: «й» из двух кодовых точек и из одной обязаны стать одной строкой.

    Иначе память озвучки и ключ состояния расходились бы на глаз одинаковых строках.
    """
    assert clean("й") == clean("й")
