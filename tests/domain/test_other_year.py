"""Зеркало :func:`torrcast.domain.other_year.other_year`: где год раздачи судится, а где нет."""

from __future__ import annotations

from torrcast.domain.other_year import other_year
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _release(year: int | None) -> Release:
    return Release(raw_name="Оно", title="Оно", year=year, quality="1080p", seeders=10)


def test_a_film_release_two_years_off_is_another_picture() -> None:
    assert other_year(_release(2014), Picture(title="Оно", year=2017))
    assert other_year(_release(2019), Picture(title="Король Лев", year=1994))


def test_the_festival_year_and_an_unknown_year_stay_with_the_picture() -> None:
    it = Picture(title="Оно", year=2017)

    assert not other_year(_release(2016), it)
    assert not other_year(_release(2018), it)
    assert not other_year(_release(None), it)
    assert not other_year(_release(2014), Picture(title="Оно", year=None))


def test_a_season_is_dated_by_its_own_year_and_is_not_judged_here() -> None:
    """Пятый сезон «Мажора» подписан 2026, сериал - 2014: это одна картина."""
    assert not other_year(_release(2026), Picture(title="Мажор", year=2014, kind="tv"))
