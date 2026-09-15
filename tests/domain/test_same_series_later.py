"""Зеркало :mod:`torrcast.domain.same_series_later`: продолжение сериала или ремейк."""

from __future__ import annotations

from dataclasses import replace

import pytest

from tests.usecases.choice.world import film
from torrcast.domain.picture import Picture
from torrcast.domain.same_series_later import same_series_later


def _show(year: int | None, *seasons: tuple[int, ...]) -> Picture:
    releases = [
        replace(film(f"Сериал {n} WEB-DL 1080p", kind="tv"), season=got[0], seasons=got)
        for n, got in enumerate(seasons)
    ]
    return Picture(title="Сериал", year=year, kind="tv", releases=releases)


@pytest.mark.parametrize(
    ("later", "year", "season"),
    [(_show(2026, (5,)), 2014, 5), (_show(2014, (1,)), 2014, 1), (_show(None, (1,)), 2014, 1)],
)
def test_a_later_season_or_the_same_year_is_the_same_series(
    later: Picture, year: int, season: int
) -> None:
    assert same_series_later(later, year, season)


@pytest.mark.parametrize(
    ("later", "year", "season"),
    [
        (_show(2005, (1,)), 1963, 1),
        (_show(2005, (1,), (2,)), 1963, 2),
        (_show(2005, (1, 2)), 1963, 2),
        (_show(2005, (2,)), 1963, 1),
        (_show(1963, (2,)), 2005, 2),
    ],
)
def test_a_remake_starts_its_own_count_and_is_not_the_same_series(
    later: Picture, year: int, season: int
) -> None:
    """«Доктор Кто» 1963 и 2005: ремейк свой счёт начинает с первого сезона."""
    assert not same_series_later(later, year, season)
