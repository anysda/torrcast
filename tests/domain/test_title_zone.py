"""Зеркало :mod:`torrcast.domain.title_zone`: часть имени раздачи, где живут названия."""

from torrcast.domain.title_zone import _title_zone


def test_the_zone_ends_where_the_year_begins() -> None:
    """После года идут пометки, и названием картины они не являются."""
    name = "Брат / Brother (1997) BDRip 1080p"

    assert _title_zone(name, (name.index("1997"), name.index("1997") + 4)) == (
        "Брат / Brother",
        False,
    )


def test_a_word_of_a_collection_is_named_apart_from_the_title() -> None:
    """«Дилогия» - это не имя картины, а признак того, что раздача сборная."""
    name = "Брат: Дилогия (1997-2000) BDRip"

    assert _title_zone(name, (name.index("1997"), name.index("1997") + 4)) == ("Брат", True)


def test_a_name_without_a_year_gives_up_the_whole_string() -> None:
    """Год не назван - резать нечем, и зоной остаётся всё имя без пометок в скобках."""
    assert _title_zone("Брат / Brother", None) == ("Брат / Brother", False)
