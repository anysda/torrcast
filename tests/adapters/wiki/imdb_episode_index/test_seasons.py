"""Чтение сезонов сериала из индекса серий IMDb."""

import sqlite3
from pathlib import Path

from torrcast.adapters.wiki.imdb_episode_index.seasons import seasons


def test_ranges_unfold_into_episode_numbers(tmp_path: Path) -> None:
    target = tmp_path / "imdb-episodes.sqlite3"
    with sqlite3.connect(target) as connection:
        connection.execute("CREATE TABLE season (parent INTEGER, season INTEGER, numbers TEXT)")
        connection.execute("INSERT INTO season VALUES (1647423, 3, '1-3,5,7-8')")

    assert seasons(target, "tt1647423") == {3: (1, 2, 3, 5, 7, 8)}
    assert seasons(target, "") == {}, "картина без IMDb-id сериалом каталога не бывает"
