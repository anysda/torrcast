"""Проверяет дисковый JSON-кэш на временном каталоге."""

from pathlib import Path

from torrcast.adapters.wiki.json_file_store import JsonFileStore


def test_round_trip_and_missing_file(tmp_path: Path) -> None:
    """Отсутствующий файл пуст, записанный словарь читается без изменений."""
    store = JsonFileStore(tmp_path / "facts.json")
    assert store.read() == {}
    store.write({"фильм": {"year": 2024}})
    assert store.read() == {"фильм": {"year": 2024}}
