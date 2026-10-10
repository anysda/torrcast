"""Зеркало :mod:`torrcast.domain.facts.map_in_year`: картина карты по году запроса."""

from __future__ import annotations

from torrcast.domain.facts.map_in_year import map_in_year
from torrcast.domain.facts.map_picture import MapPicture

SERIES = MapPicture("Звери.", 2016, True, "Animals.", 4736)
FILM = MapPicture("Брат", 1997, False, "Brat", 29581)


def test_a_film_is_its_year_give_or_take_one() -> None:
    assert map_in_year(FILM, 1997)
    assert map_in_year(FILM, 1998), "год ± 1: фестиваль и прокат расходятся"
    assert not map_in_year(FILM, 2000)


def test_a_series_is_its_first_year_and_not_any_later_one() -> None:
    """🔴 «Animals 2026» - не сериал 2016 года: год назван, и он не его."""
    assert map_in_year(SERIES, 2016)
    assert map_in_year(SERIES, 2017)
    assert not map_in_year(SERIES, 2026), "сериал 2016 года не узнаётся по 2026-му"
    assert not map_in_year(SERIES, 2010)


def test_a_picture_without_a_year_is_no_year_at_all() -> None:
    assert not map_in_year(MapPicture("Без года", None, False, "", 1), 2026)
