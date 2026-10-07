"""The local JacRed catalogue never asks its former API."""

import importlib.util
import sqlite3
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "jacred_indexer", Path(__file__).parents[1] / "scripts/jacred-indexer.py"
)
assert SPEC and SPEC.loader
adapter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(adapter)


def _index(path: Path) -> None:
    db = sqlite3.connect(path)
    db.executescript(
        """CREATE TABLE release(id INTEGER PRIMARY KEY,title,magnet,size,seeders,leechers,created);
CREATE VIRTUAL TABLE search USING fts5(title,content='release',content_rowid='id');
CREATE TRIGGER release_ai AFTER INSERT ON release BEGIN
 INSERT INTO search(rowid,title) VALUES(new.id,new.title); END;"""
    )
    db.execute(
        "INSERT INTO release(title,magnet,size,seeders,leechers,created) VALUES(?,?,?,?,?,?)",
        ("Матрица 1999 1080p Dub", "magnet:?xt=urn:btih:a", 8, 42, 3, "2026-08-11T00:00:00"),
    )
    db.execute(
        "INSERT INTO release(title,magnet,size,seeders,leechers,created) VALUES(?,?,?,?,?,?)",
        ("The Matrix 1999 Dub", "magnet:?xt=urn:btih:b", 8, 41, 3, "2026-08-11T00:00:00"),
    )
    db.commit()
    db.close()


def test_local_rows_become_cardigann_rows(tmp_path: Path) -> None:
    index = tmp_path / "index.sqlite"
    _index(index)
    assert adapter.search("матрица", index) == [
        {
            "title": "Матрица 1999 1080p Dub",
            "magnet": "magnet:?xt=urn:btih:a",
            "size": 8,
            "seeders": 42,
            "leechers": 3,
            "date": "1786406400",
        }
    ]


def test_missing_or_cut_index_is_an_empty_source(tmp_path: Path) -> None:
    assert adapter.search("матрица", tmp_path / "absent.sqlite") == []
    broken = tmp_path / "broken.sqlite"
    broken.write_text("not sqlite")
    assert adapter.search("матрица", broken) == []


def test_joined_names_are_union_not_an_impossible_fts_intersection(tmp_path: Path) -> None:
    index = tmp_path / "index.sqlite"
    _index(index)

    assert {row["magnet"] for row in adapter.search("Матрица | The Matrix", index)} == {
        "magnet:?xt=urn:btih:a",
        "magnet:?xt=urn:btih:b",
    }
