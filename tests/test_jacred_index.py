"""The FileDB reader publishes a complete FTS catalogue, or leaves the old one alone."""

import gzip
import importlib.util
import sqlite3
from collections.abc import Iterator
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "jacred_index", Path(__file__).parents[1] / "scripts/jacred-index.py"
)
assert SPEC and SPEC.loader
index = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(index)


def test_build_reads_gzip_objects_and_publishes_a_prefix_search(tmp_path: Path) -> None:
    source = tmp_path / "filedb"
    source.mkdir()
    with gzip.open(source / "one.json.gz", "wt", encoding="utf-8") as out:
        out.write(
            '{"one":{"title":"Матрица 1999 Dub","magnet":"magnet:?xt=urn:btih:a",'
            '"size":8,"sid":42,"pir":3,"createTime":"2026-08-11T00:00:00"}}'
        )
    target = tmp_path / "index.sqlite"

    assert index.build(source, target)[0] == 1
    with sqlite3.connect(target) as db:
        found = db.execute(
            "SELECT title FROM search WHERE search MATCH ?", ('"матри"*',)
        ).fetchall()
    assert found == [("Матрица 1999 Dub",)]


def test_an_empty_source_keeps_the_published_index(tmp_path: Path) -> None:
    source = tmp_path / "filedb"
    source.mkdir()
    target = tmp_path / "index.sqlite"
    target.write_bytes(b"known-good")

    with pytest.raises(ValueError, match="no usable releases"):
        index.build(source, target)

    assert target.read_bytes() == b"known-good"
    assert not target.with_suffix(".new").exists()


def test_a_build_interrupted_before_replace_keeps_the_live_index(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Power loss while constructing ``.new`` must not corrupt the served catalogue."""
    source = tmp_path / "filedb"
    source.mkdir()
    target = tmp_path / "index.sqlite"
    old = sqlite3.connect(target)
    old.execute("CREATE TABLE known(value TEXT)")
    old.execute("INSERT INTO known VALUES ('published')")
    old.commit()
    old.close()

    def cut_records(_root: Path) -> Iterator[tuple[str, str, int, int, int, str]]:
        yield ("Матрица", "magnet:?xt=urn:btih:a", 8, 42, 3, "2026-08-11")
        raise OSError("simulated power cut")

    monkeypatch.setattr(index, "records", cut_records)

    with pytest.raises(OSError, match="power cut"):
        index.build(source, target)

    with sqlite3.connect(target) as published:
        assert published.execute("SELECT value FROM known").fetchall() == [("published",)]


def test_build_checks_for_playback_before_each_batch(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    source = tmp_path / "filedb"
    source.mkdir()
    target = tmp_path / "index.sqlite"
    rows = [("Матрица", "magnet:?xt=urn:btih:a", 8, 42, 3, "2026-08-11")] * 1001
    monkeypatch.setattr(index, "records", lambda _root: iter(rows))
    waits: list[None] = []

    assert index.build(source, target, lambda: waits.append(None))[0] == 1001
    assert len(waits) == 1002
