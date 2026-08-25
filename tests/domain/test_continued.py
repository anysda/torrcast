"""Зеркало :mod:`torrcast.domain.continued`: две горсти серий, идущие подряд."""

from collections.abc import Callable

from torrcast.domain.continued import _continued
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release


def _series(
    title: str, year: int, episodes: tuple[int, ...] = (), season: int | None = None
) -> Picture:
    release = Release(
        raw_name=title, title=title, year=year, episodes=episodes, season=season, kind="tv"
    )
    return Picture(title=title, year=year, kind="tv", releases=[release])


def _joined() -> tuple[Callable[[int, int], None], list[tuple[int, int]]]:
    seen: list[tuple[int, int]] = []
    return (lambda left, right: seen.append((left, right))), seen


def test_episodes_that_go_on_where_the_others_stopped_become_one_chain() -> None:
    """Серии 4-6 после 1-3 - это тот же сериал, разложенный по двум раздачам."""
    pictures = [_series("A", 2019, episodes=(1, 2, 3)), _series("B", 2020, episodes=(4, 5, 6))]
    union, seen = _joined()

    assert _continued(pictures, [[0], [1]], union) == [[0, 1]]
    assert seen == [(0, 1)]


def test_a_gap_between_the_runs_leaves_them_apart() -> None:
    """Между 3 и 30 серии потеряны, и склейка тут была бы выдумкой."""
    pictures = [_series("A", 2019, episodes=(1, 2, 3)), _series("B", 2020, episodes=(30, 31))]
    union, seen = _joined()

    assert _continued(pictures, [[0], [1]], union) == [[0], [1]]
    assert seen == []


def test_a_run_that_starts_from_the_first_episode_is_its_own_series() -> None:
    """Обе горсти начинаются с первой серии - это два сериала, а не один длинный."""
    pictures = [_series("A", 2019, episodes=(1, 2)), _series("B", 2020, episodes=(1, 2))]
    union, seen = _joined()

    assert _continued(pictures, [[0], [1]], union) == [[0], [1]]
    assert seen == []


def test_seasons_continue_the_same_way_episodes_do() -> None:
    """Второй сезон после первого - тот же сериал: мера тут та же, что у серий."""
    pictures = [_series("A", 2019, season=1), _series("B", 2020, season=2)]
    union, seen = _joined()

    assert _continued(pictures, [[0], [1]], union) == [[0, 1]]
    assert seen == [(0, 1)]


def test_pictures_that_are_not_series_are_never_joined() -> None:
    """У кино нумерации серий нет вовсе, и правило продолжения к нему не применяется."""
    movies = [Picture(title="A", year=2019), Picture(title="B", year=2020)]
    union, seen = _joined()

    assert _continued(movies, [[0], [1]], union) == [[0], [1]]
    assert seen == []
