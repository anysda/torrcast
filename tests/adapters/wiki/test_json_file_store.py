"""Проверяет дисковый JSON-кэш на временном каталоге."""

from pathlib import Path

from torrcast.adapters.wiki.json_file_store import JsonFileStore


def test_round_trip_and_missing_file(tmp_path: Path) -> None:
    """Отсутствующий файл пуст, записанный словарь читается без изменений."""
    store = JsonFileStore(tmp_path / "facts.json")
    assert store.read() == {}
    store.write({"фильм": {"year": 2024}})
    assert store.read() == {"фильм": {"year": 2024}}


def test_a_file_changed_behind_the_store_is_read_again(tmp_path: Path) -> None:
    """Разобранное отдаётся без чтения, пока файл тот же; чужая запись читается заново."""
    store = JsonFileStore(tmp_path / "facts.json")
    store.write({"a": 1})
    store.read()["b"] = 2
    assert store.read() == {"a": 1}, "правка ответа протекла в разобранное"
    (tmp_path / "facts.json").write_text('{"a": 1, "c": 333}', encoding="utf-8")
    assert store.read() == {"a": 1, "c": 333}
