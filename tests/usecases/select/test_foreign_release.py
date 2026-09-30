"""Зеркало :func:`foreign_release`: кого из пула очередь отбора не спрашивает."""

from __future__ import annotations

from torrcast.domain.episode import Episode
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.usecases.select.foreign_release import foreign_release


def _release(
    year: int | None,
    *,
    season: int | None = None,
    episodes: tuple[int, ...] = (),
    original: str | None = None,
) -> Release:
    return Release(
        raw_name="Оно",
        title="Оно",
        original=original,
        year=year,
        quality="1080p",
        seeders=10,
        season=season,
        episodes=episodes,
    )


def test_a_film_release_of_another_year_is_foreign_to_the_film() -> None:
    it = Picture(title="Оно", year=2017)

    assert foreign_release(_release(2014), it, None)
    assert not foreign_release(_release(2017), it, None)


def test_a_season_pack_without_the_asked_episode_is_foreign_to_the_episode() -> None:
    show = Picture(title="Мажор", year=2014, kind="tv")

    assert foreign_release(_release(2026, season=5, episodes=(1, 2)), show, Episode(5, 7))
    assert not foreign_release(_release(2026, season=5, episodes=(7,)), show, Episode(5, 7))


def test_a_series_of_another_work_by_the_original_is_foreign_to_the_episode() -> None:
    naruto = Picture(title="Наруто", year=2002, kind="tv", original="Naruto")

    assert foreign_release(
        _release(2007, original="Naruto: Shippuuden", season=1), naruto, Episode(1, 1)
    )
