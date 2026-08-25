"""Зеркало :mod:`torrcast.domain.split_titles`: имена картины, разделённые косой чертой."""

from torrcast.domain.split_titles import _split_titles


def test_the_russian_name_leads_and_the_latin_one_follows() -> None:
    """Человеку показывается русское имя, а искать вторым заходом надо латинским."""
    assert _split_titles("Брат / Brother") == ("Брат", "Brother", ())


def test_every_further_name_becomes_an_alias() -> None:
    """Третьим именем картину зовут другие трекеры: это вход в неё, а не мусор."""
    assert _split_titles("Брат / Brother / Bratan") == ("Брат", "Brother", ("Bratan",))


def test_a_zone_of_one_latin_name_has_no_second_one() -> None:
    assert _split_titles("Brother") == ("Brother", None, ())


def test_an_empty_zone_is_named_as_unknown_rather_than_left_blank() -> None:
    """Пустое название сделало бы картину безымянной строкой в меню."""
    assert _split_titles("  ") == ("?", None, ())
