"""Зеркало :mod:`torrcast.domain.glued_year`: год склеенной картины."""

from torrcast.domain.glued_year import _glued_year
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _release(year: int) -> Release:
    return Release(raw_name="Брат", title="Брат", year=year)


def test_a_film_takes_the_year_most_of_its_releases_wrote() -> None:
    """Год фильма пишут сами раздачи, и правы те, которых больше."""
    found = _glued_year(
        "movie",
        [Picture(title="Брат", year=2005)],
        [_release(1997), _release(1997), _release(1999)],
    )

    assert found == 1997


def test_a_series_takes_the_year_it_started() -> None:
    """У сериала год - это год начала, а не тот, что чаще написан на сезонах."""
    merged = [Picture(title="Сериал", year=2005), Picture(title="Сериал", year=2003)]

    assert _glued_year("tv", merged, [_release(2019), _release(2019)]) == 2003


def test_a_film_without_a_single_dated_release_falls_back_to_the_pictures() -> None:
    merged = [Picture(title="Брат", year=1997)]

    assert _glued_year("movie", merged, [Release(raw_name="Брат", title="Брат")]) == 1997


def test_a_year_nobody_named_stays_unnamed() -> None:
    assert _glued_year("movie", [Picture(title="Брат", year=None)], []) is None
