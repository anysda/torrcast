"""Зеркало :mod:`torrcast.domain.season_numbering`: номер серии - место в сезоне."""

from __future__ import annotations

from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.season_numbering import season_numbering


def _found(*pairs: tuple[int, int]) -> list[EpisodeFile]:
    return [EpisodeFile(i, s, e, f"{s}-{e}.mkv", 1) for i, (s, e) in enumerate(pairs, start=1)]


def _at(files: list[EpisodeFile]) -> list[tuple[int, int]]:
    return [(f.season, f.episode) for f in files]


def test_hundreds_become_the_season_only_under_a_season_folder() -> None:
    found = _found((1, 101), (1, 102), (2, 201), (2, 202))
    folders = {1: 1, 2: 1, 3: 2, 4: 2}
    assert _at(season_numbering(found, folders)) == [(1, 1), (1, 2), (2, 1), (2, 2)]
    assert _at(season_numbering(found, {})) == _at(found), "без каталога сотни не сезон"


def test_a_chained_running_count_restarts_and_a_gap_keeps_it() -> None:
    chained = _found((1, 1), (1, 2), (2, 3), (2, 4), (3, 5))
    assert _at(season_numbering(chained, {})) == [(1, 1), (1, 2), (2, 1), (2, 2), (3, 1)]
    gap = _found((1, 1), (1, 2), (2, 4), (2, 5))
    assert _at(season_numbering(gap, {})) == _at(gap)
    alone = _found((3, 41), (3, 42))
    assert _at(season_numbering(alone, {})) == _at(alone), "одинокий сезон начала не знает"
    normal = _found((1, 1), (1, 2), (2, 1), (2, 2))
    assert _at(season_numbering(normal, {})) == _at(normal)
