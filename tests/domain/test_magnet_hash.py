"""Инфохэш из магнита: имя, по которому раздачу узнают в следующем поиске."""

from __future__ import annotations

from torrcast.domain.magnet_hash import magnet_hash

HEX = "4f2c1a90bd9e3f1fbaa1a8b8b7c0d1e2f3a4b5c6"
BASE32 = "MFRGGZDFMZTWQ2LKNNWG23TP"


def test_the_hash_is_taken_and_lowercased() -> None:
    """Регистр магнита не меняет имени: сверяются два ответа поиска, а не две строки."""
    assert magnet_hash(f"magnet:?xt=urn:btih:{HEX.upper()}&dn=Тачки") == HEX
    assert magnet_hash(f"magnet:?dn=Тачки&xt=URN:BTIH:{HEX}") == HEX


def test_the_base32_form_survives_too() -> None:
    """Base32 - тоже имя раздачи: сверять его есть с чем, и терять его нельзя."""
    assert magnet_hash(f"magnet:?xt=urn:btih:{BASE32}&dn=x") == BASE32.lower()


def test_percent_encoded_colons_are_still_a_hash() -> None:
    """Трекер вправе закодировать двоеточия - раздача от этого другой не становится."""
    assert magnet_hash(f"magnet:?xt=urn%3Abtih%3A{HEX}") == HEX


def test_the_first_btih_wins_among_several_topics() -> None:
    """У магнита бывает несколько ``xt``; раздача - та, что названа по ``btih``."""
    assert magnet_hash(f"magnet:?xt=urn:ed2k:abc&xt=urn:btih:{HEX}&dn=x") == HEX


def test_what_is_not_a_release_gives_nothing() -> None:
    """Не раздача - пусто: по пустому имени показ ищет заново, а не берёт наугад.

    ``xt.1`` - часть многосоставного магнита, а не эта раздача, и её именем быть не вправе.
    """
    assert magnet_hash(f"magnet:?xt.1=urn:btih:{HEX}") == ""
    assert magnet_hash("magnet:?xt=urn:ed2k:abc") == ""
    assert magnet_hash("magnet:?xt=1&dn=x") == ""
    assert magnet_hash("magnet:?xt=urn:btih:&dn=x") == ""
    assert magnet_hash("") == ""
