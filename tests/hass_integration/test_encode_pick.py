"""Адрес найденной картинки: что уезжает на карточку под одной находкой."""

from __future__ import annotations

from custom_components.torrcast.decode_pick import decode_pick
from custom_components.torrcast.encode_pick import encode_pick


def test_the_id_carries_both_the_query_and_the_number_of_the_pick() -> None:
    """Номер человек читает глазами в журнале, запрос уезжает целиком."""
    assert (
        encode_pick("чернобыль", 3)
        == "torrcast://pick/3?q=%D1%87%D0%B5%D1%80%D0%BD%D0%BE%D0%B1%D1%8B%D0%BB%D1%8C"
    )


def test_a_query_with_slashes_and_ampersands_survives_the_round_trip() -> None:
    """🔴 Запрос человек пишет свободно, и в нём бывает всё, что рвёт адрес.

    Косая черта уехала бы в путь и увела бы номер находки, амперсанд завёл бы второй
    параметр. Проба идёт через настоящее чтение, а не через глаз: пара обязана сойтись.
    """
    query = "кто/что & как?"

    assert decode_pick(encode_pick(query, 12)) == (query, 12)
