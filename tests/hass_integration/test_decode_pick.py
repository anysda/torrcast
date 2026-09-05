"""Чтение адреса найденной картинки: где номер находки, а где просто набранный запрос."""

from __future__ import annotations

from custom_components.torrcast.decode_pick import decode_pick


def test_a_bare_query_is_not_a_pick() -> None:
    """Свободный текст человека - это запрос, а не находка, и читается как раньше."""
    assert decode_pick("игра престолов s01e03") is None


def test_a_foreign_scheme_is_not_a_pick() -> None:
    """Чужой адрес из другого источника Home Assistant сюда не заезжает."""
    assert decode_pick("media-source://media_source/local/film.mp4") is None


def test_an_id_without_a_number_is_not_a_pick() -> None:
    """Номер находки - число; всё прочее в пути читается как «не находка»."""
    assert decode_pick("torrcast://pick/первая?q=чернобыль") is None


def test_a_pick_without_a_query_still_names_its_number() -> None:
    """Запрос мог и потеряться, но номер находки при этом остаётся читаемым."""
    assert decode_pick("torrcast://pick/2") == ("", 2)
