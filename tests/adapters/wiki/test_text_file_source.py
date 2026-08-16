"""Проверяет дисковый источник строк на временном каталоге."""

from pathlib import Path

from torrcast.adapters.wiki.text_file_source import TextFileSource


def test_reads_lines_and_tolerates_missing_file(tmp_path: Path) -> None:
    """Строки читаются как есть, отсутствующий файл даёт пустой поток."""
    path = tmp_path / "ratings.tsv"
    path.write_text("шапка\nстрока\n", encoding="utf-8")
    source = TextFileSource()
    assert list(source.lines(path)) == ["шапка\n", "строка\n"]
    assert list(source.lines(tmp_path / "нет-файла")) == []
