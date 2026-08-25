"""Зеркало :mod:`torrcast.domain.seasons_named`: какие сезоны названы раздачами картины."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.seasons_named import seasons_named


def _series(*releases: Release) -> Picture:
    return Picture(title="Сериал", year=2019, kind="tv", releases=list(releases))


def _release(season: int | None = None, seasons: tuple[int, ...] = ()) -> Release:
    return Release(raw_name="Сериал", title="Сериал", season=season, seasons=seasons)


def test_the_named_seasons_come_sorted_and_without_repeats() -> None:
    """Сезон называют несколько раздач, а список у картины один и по порядку."""
    picture = _series(_release(season=3), _release(season=1), _release(season=3))

    assert seasons_named(picture) == (1, 3)


def test_a_release_that_holds_several_seasons_names_them_all() -> None:
    assert seasons_named(_series(_release(seasons=(2, 3)))) == (2, 3)


def test_a_picture_whose_releases_kept_silent_names_nothing() -> None:
    assert seasons_named(_series(_release())) == ()
