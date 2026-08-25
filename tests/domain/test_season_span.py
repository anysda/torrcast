"""Зеркало :mod:`torrcast.domain.season_span`: сезоны, обещанные именем раздачи."""

from torrcast.domain.season_span import _season_span


def test_a_named_range_gives_every_season_inside_it() -> None:
    assert _season_span("Сериал 1-3 сезоны 1080p") == (1, 2, 3)


def test_a_name_that_promises_no_range_gives_nothing() -> None:
    assert _season_span("Сериал 2 сезон") == ()


def test_a_backwards_range_is_not_a_range() -> None:
    assert _season_span("Сериал 3-1 сезоны") == ()
