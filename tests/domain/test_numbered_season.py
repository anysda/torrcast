"""Зеркало :mod:`torrcast.domain.numbered_season`: число при имени сериала - это сезон."""

from torrcast.domain.numbered_season import _numbered_season
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _series(part: int | None, season: int | None) -> Picture:
    release = Release(raw_name="Сериал", title="Сериал", season=season, kind="tv")
    return Picture(title="Сериал", year=2019, kind="tv", part=part, releases=[release])


def test_a_number_the_releases_confirm_as_a_season_is_a_season() -> None:
    """Поручительство тут одно: раздачи назвали ровно тот сезон, что стоит при имени."""
    assert _numbered_season(_series(part=2, season=2))


def test_a_number_the_releases_call_another_season_is_not_confirmed() -> None:
    assert not _numbered_season(_series(part=2, season=3))


def test_a_number_no_release_confirms_stays_a_part_number() -> None:
    assert not _numbered_season(_series(part=2, season=None))


def test_a_film_has_no_seasons_at_all() -> None:
    movie = Picture(title="Брат 2", year=2000, part=2)

    assert not _numbered_season(movie)
