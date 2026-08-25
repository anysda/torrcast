"""Зеркало :mod:`torrcast.domain.picture_season_span`: какие сезоны картина покрывает."""

from torrcast.domain.picture import Picture
from torrcast.domain.picture_season_span import _picture_season_span
from torrcast.domain.release import Release


def _series(*releases: Release) -> Picture:
    return Picture(title="Сериал", year=2019, kind="tv", releases=list(releases))


def _season(season: int | None = None, seasons: tuple[int, ...] = ()) -> Release:
    return Release(raw_name="Сериал", title="Сериал", season=season, seasons=seasons, kind="tv")


def test_the_span_runs_from_the_earliest_season_to_the_latest() -> None:
    """Сезоны приходят разными раздачами, а вопрос к картине один: с какого по какой."""
    assert _picture_season_span(_series(_season(season=3), _season(season=1))) == (1, 3)


def test_a_release_that_holds_several_seasons_counts_them_all() -> None:
    assert _picture_season_span(_series(_season(seasons=(2, 3, 4)))) == (2, 4)


def test_a_picture_whose_releases_name_no_season_has_no_span() -> None:
    assert _picture_season_span(_series(_season())) is None
