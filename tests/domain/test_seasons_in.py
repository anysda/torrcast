"""Зеркало :mod:`torrcast.domain.seasons_in`: какие сезоны названы вслух самими именами."""

from torrcast.domain.release import Release
from torrcast.domain.seasons_in import seasons_in


def _release(season: int | None = None, seasons: tuple[int, ...] = ()) -> Release:
    return Release(raw_name="Сериал", title="Сериал", season=season, seasons=seasons)


def test_the_named_seasons_come_sorted_and_without_repeats() -> None:
    """Сезон называют несколько раздач, а список у горсти один и по порядку."""
    assert seasons_in([_release(season=3), _release(season=1), _release(season=3)]) == (1, 3)


def test_a_release_that_holds_several_seasons_names_them_all() -> None:
    assert seasons_in([_release(seasons=(2, 3))]) == (2, 3)


def test_a_handful_that_kept_silent_names_nothing() -> None:
    """Молчание - это пустой список, а не догадка про первый сезон."""
    assert seasons_in([_release()]) == ()
