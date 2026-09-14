"""Названные в имени сезоны доходят до общего разбора раздачи."""

from __future__ import annotations

import pytest

from torrcast.domain.parse_release_name import parse_release_name


@pytest.mark.parametrize(
    ("name", "season", "seasons"),
    (
        ("Сериал / Series / Сезон: 9 / Серии: 1-10 из 10 WEB-DL 1080p", 9, ()),
        ("Сериал / Series / Сезоны: 1-5 / Серии: 1-21 WEB-DL 1080p", 1, (1, 2, 3, 4, 5)),
        ("Series S01-S05 WEB-DL 1080p", 1, (1, 2, 3, 4, 5)),
        ("Сериал / Series / 1-4 сезон WEB-DL 1080p", 1, (1, 2, 3, 4)),
        ("Сериал / Series / Сезон: 1, 2 / Серии: 1-21 WEB-DL 1080p", 1, (1, 2)),
    ),
)
def test_named_season_forms_are_series_and_cover_every_named_season(
    name: str, season: int, seasons: tuple[int, ...]
) -> None:
    release = parse_release_name(name)

    assert release.kind == "tv"
    assert release.season == season
    assert release.seasons == seasons
    assert all(release.covers(number) for number in seasons or (season,))
