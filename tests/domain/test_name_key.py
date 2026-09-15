"""Зеркало ключа имени: слаг без диакритики."""

from __future__ import annotations

from torrcast.domain.name_key import name_key


def test_diacritics_and_punctuation_do_not_part_one_name() -> None:
    assert name_key("Naruto: Shippûden") == name_key("naruto shippuden") == "naruto-shippuden"
    assert name_key("Ёлки") == name_key("елки")


def test_an_absent_name_is_an_empty_key() -> None:
    assert name_key(None) == name_key("") == name_key(" - ") == ""
