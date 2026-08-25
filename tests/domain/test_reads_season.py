"""Зеркало :mod:`torrcast.domain.reads_season`: номер запроса читается как сезон."""

from torrcast.domain.picture import Picture
from torrcast.domain.reads_season import reads_season
from torrcast.domain.release import Release


def _series(part: int | None, season: int | None, year: int = 2019) -> Picture:
    release = Release(raw_name="Сериал", title="Сериал", season=season, kind="tv")
    return Picture(title="Сериал", year=year, kind="tv", part=part, releases=[release])


def test_a_pool_of_series_whose_numbers_are_seasons_reads_the_number_as_a_season() -> None:
    """«Сериал 2» у сериала - это второй сезон, а не вторая часть франшизы."""
    assert reads_season([_series(part=None, season=1, year=2018), _series(part=2, season=2)])


def test_a_number_no_release_confirms_keeps_the_pool_a_franchise() -> None:
    assert not reads_season([_series(part=2, season=None)])


def test_a_pool_that_starts_with_a_film_is_a_franchise() -> None:
    """Первой в линейке стоит картина, и если это кино - номер значит часть."""
    movie = Picture(title="Кино", year=2000)

    assert not reads_season([movie, _series(part=None, season=1)])


def test_an_empty_pool_reads_nothing() -> None:
    assert not reads_season([])
