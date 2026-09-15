"""Чтение одного имени из дискового индекса IMDb."""

from pathlib import Path

from tests.articles import RU_MAP
from torrcast.adapters.wiki.imdb_name_index.build import build
from torrcast.adapters.wiki.imdb_name_index.rows import rows


def test_a_missing_index_is_silence(tmp_path: Path) -> None:
    """Без индекса вызывающий сохраняет прежний запасной путь к TSV."""
    path = tmp_path / "imdb-ru-names.sqlite3"

    assert rows(path, "Мы") is None


def test_a_ready_index_returns_only_its_named_rows(tmp_path: Path) -> None:
    names = tmp_path / "imdb-ru-names.tsv"
    names.write_text(RU_MAP, encoding="utf-8")
    assert build(names) is True

    assert [row[4] for row in rows(names.with_suffix(".sqlite3"), "Пятая власть") or []] == [
        "Пятая власть",
        "Пятая власть",
    ]
