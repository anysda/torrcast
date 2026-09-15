"""Сборка дискового индекса серий IMDb из выгрузки ``title.episode.tsv.gz``."""

import gzip
import os
from pathlib import Path

from torrcast.adapters.wiki.imdb_episode_index.build import build
from torrcast.adapters.wiki.imdb_episode_index.seasons import seasons

HEAD = "tconst\tparentTconst\tseasonNumber\tepisodeNumber\n"
FUTURAMA = "".join(f"tt9{n:06d}\ttt0149460\t1\t{n}\n" for n in (3, 1, 2, 5, 9))
UNNUMBERED = "tt8000001\ttt0149460\t\\N\t\\N\ntt8000002\ttt0149460\t2\t\\N\n"


def _dump(path: Path, body: str) -> str:
    with gzip.open(path, "wt", encoding="utf-8") as out:
        out.write(HEAD + body)
    return path.as_uri()


def test_the_index_answers_a_series_by_its_imdb_id(tmp_path: Path) -> None:
    url = _dump(tmp_path / "title.episode.tsv.gz", FUTURAMA + UNNUMBERED)
    target = tmp_path / "imdb-episodes.sqlite3"

    assert build(url, target) is True
    assert seasons(target, "tt0149460") == {1: (1, 2, 3, 5, 9)}, "без номера строки нет"
    assert seasons(target, "tt0000001") == {}, "сериала нет в выгрузке"
    assert seasons(tmp_path / "missing.sqlite3", "tt0149460") is None, "индекса нет"


def test_an_unchanged_dump_does_not_rebuild_its_index(tmp_path: Path) -> None:
    """Установщик и суточное обновление качают выгрузку заново только изменившейся."""
    url = _dump(tmp_path / "title.episode.tsv.gz", FUTURAMA)
    target = tmp_path / "imdb-episodes.sqlite3"

    assert build(url, target) is True
    assert build(url, target) is False


def test_a_changed_dump_rebuilds_its_index(tmp_path: Path) -> None:
    dump = tmp_path / "title.episode.tsv.gz"
    target = tmp_path / "imdb-episodes.sqlite3"
    assert build(_dump(dump, FUTURAMA), target) is True

    url = _dump(dump, FUTURAMA + "tt7000001\ttt0149460\t2\t1\n")
    os.utime(dump, (1, 1))

    assert build(url, target) is True
    assert seasons(target, "tt0149460") == {1: (1, 2, 3, 5, 9), 2: (1,)}


def test_a_broken_dump_keeps_the_previous_index(tmp_path: Path) -> None:
    dump = tmp_path / "title.episode.tsv.gz"
    target = tmp_path / "imdb-episodes.sqlite3"
    assert build(_dump(dump, FUTURAMA), target) is True

    dump.write_bytes(gzip.compress((HEAD + FUTURAMA).encode())[:40])

    assert build(dump.as_uri(), target) is False
    assert seasons(target, "tt0149460") == {1: (1, 2, 3, 5, 9)}
    assert sorted(path.name for path in tmp_path.iterdir()) == sorted([dump.name, target.name])
