"""Обновление индекса серий идёт отдельным процессом, а не в потоке службы."""

import gzip
from collections.abc import Sequence
from pathlib import Path

from torrcast.adapters.wiki.imdb_episode_index.build import build
from torrcast.adapters.wiki.imdb_episode_index.refresh import refresh
from torrcast.adapters.wiki.imdb_episode_index.seasons import seasons


def test_the_build_runs_as_its_own_process(tmp_path: Path) -> None:
    dump = tmp_path / "title.episode.tsv.gz"
    dump.write_bytes(gzip.compress(b"tconst\tparentTconst\ts\te\ntt1\ttt0149460\t1\t1\n"))
    target = tmp_path / "imdb-episodes.sqlite3"
    seen: list[Sequence[str]] = []

    def run(command: Sequence[str]) -> int:
        seen.append(command)
        *_program, module, url, where = command
        assert module == "torrcast.adapters.wiki.imdb_episode_index.build"
        return 0 if build(url, Path(where)) else 1

    assert refresh(dump.as_uri(), target, run) is True
    assert seasons(target, "tt0149460") == {1: (1,)}
    assert seen[0][-4] == "-m", "сборка идёт своим интерпретатором, а не потоком службы"


def test_a_missing_interpreter_is_a_failed_round_not_a_crash(tmp_path: Path) -> None:
    def run(command: Sequence[str]) -> int:
        raise FileNotFoundError(command[0])

    assert refresh("file:///nope", tmp_path / "index.sqlite3", run) is False
