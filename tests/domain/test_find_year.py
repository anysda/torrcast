"""Зеркало :mod:`torrcast.domain.find_year`: год картины и его место в имени."""

from torrcast.domain.find_year import _find_year


def test_the_year_comes_back_with_the_place_it_was_taken_from() -> None:
    """Место нужно разбору: по нему имя режется на название и пометки."""
    year, span = _find_year("Брат (1997) BDRip")

    assert year == 1997
    assert span is not None
    assert "1997" in "Брат (1997) BDRip"[span[0] : span[1]]


def test_a_name_without_a_year_says_so_by_both_answers() -> None:
    assert _find_year("Брат BDRip") == (None, None)


def test_the_resolution_is_not_taken_for_a_year() -> None:
    """1080 и 2160 стоят в имени всегда, и годом ни одно из них не является."""
    assert _find_year("Брат 1080p BDRip") == (None, None)
