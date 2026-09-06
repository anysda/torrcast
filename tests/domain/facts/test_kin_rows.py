"""Зеркало :mod:`torrcast.domain.facts.kin_rows`: родня в ряду кэша и обратно."""

from torrcast.domain.facts.kin import Kin
from torrcast.domain.facts.kin_rows import _kin_key, _kin_row, _row_kin


def test_the_key_names_the_entity_it_was_asked_about() -> None:
    """Ключ ряда родни отличим от ключей паспортов и справки в том же файле."""
    assert _kin_key("Q105598") == "kin|Q105598"
    assert _kin_key("Q105598") != _kin_key("Q46717")


def test_kin_survives_the_round_trip_through_a_row() -> None:
    """Что записано в ряд, то и читается из него - тем же значением."""
    found = [
        Kin("Q105993", "Крепкий орешек 2", 1990),
        Kin("Q72276", "A Good Day to Die Hard", None),
    ]
    assert _row_kin(_kin_row(found)) == found


def test_an_unasked_row_reads_as_none_and_not_as_an_empty_shelf() -> None:
    """``None`` в хранилище значит «не спрашивали» - это не то же самое, что пустая полка."""
    assert _row_kin(None) is None
    assert _row_kin("мусор") is None
    assert _row_kin([]) == []
