"""Зеркало :mod:`torrcast.domain.run_span`: сплошная линейка серий у картины."""

from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.run_span import _run_span


def _series(*releases: Release) -> Picture:
    return Picture(title="Сериал", year=2019, kind="tv", releases=list(releases))


def _release(
    episodes: tuple[int, ...] = (), season: int | None = None, seasons: tuple[int, ...] = ()
) -> Release:
    return Release(
        raw_name="Сериал", title="Сериал", episodes=episodes, season=season, seasons=seasons
    )


def test_the_run_goes_from_the_first_episode_to_the_last() -> None:
    """Сквозная нумерация приходит разными раздачами, а линейка у картины одна."""
    assert _run_span(_series(_release(episodes=(4, 5, 6)), _release(episodes=(1, 2, 3)))) == (1, 6)


def test_a_release_that_names_its_season_is_not_a_straight_run() -> None:
    """С сезоном номер серии считается внутри него, и сквозной линейки тут нет."""
    assert _run_span(_series(_release(episodes=(1, 2), season=1))) is None


def test_a_picture_without_numbered_episodes_has_no_run() -> None:
    assert _run_span(_series(_release())) is None
