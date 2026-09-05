"""Чтение того, что человек набрал в поле мгновенного ввода."""

from __future__ import annotations

from custom_components.torrcast.const import INSTANT_ID
from custom_components.torrcast.decode_message import decode_message


def test_the_typed_words_come_back_off_the_id() -> None:
    """Диалог играет id самого узла с набранными словами в `message`."""
    assert decode_message(f"{INSTANT_ID}?message=%D1%82%D0%B0%D1%87%D0%BA%D0%B8") == "тачки"


def test_spaces_around_the_typed_words_are_dropped() -> None:
    """Человек ставит пробел мимоходом; серву он не нужен."""
    assert decode_message(f"{INSTANT_ID}?message=%20%20тачки%20%20") == "тачки"


def test_an_empty_field_is_read_as_nothing_typed() -> None:
    """Поле нажали, ничего не набрав: это пустая команда, а не отсутствие поля."""
    assert decode_message(INSTANT_ID) == ""


def test_an_id_from_elsewhere_is_not_a_typed_command() -> None:
    """🔴 Пустая строка и `None` тут - разные ответы, и путать их нельзя.

    `None` значит «ехало не из поля», и вызывающий идёт дальше своей дорогой; пустая
    строка значит «поле пустое». Свернись одно в другое - обычный запрос человека уехал
    бы на серв пустым.
    """
    assert decode_message("чернобыль") is None
    assert decode_message("torrcast://pick/1?q=чернобыль") is None
