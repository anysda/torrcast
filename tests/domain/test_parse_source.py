"""Зеркало :mod:`torrcast.domain.parse_source`: откуда снята раздача."""

from torrcast.domain.parse_source import _parse_source


def test_the_source_is_read_out_of_the_name() -> None:
    assert _parse_source("Кино 1080p BDRip") == "BDRip"
    assert _parse_source("Кино WEB-DL 1080p") == "WEB-DL"


def test_a_name_without_a_source_leaves_it_unnamed() -> None:
    assert _parse_source("Кино 1997") is None
