"""Проверяет разбор файлов раздачи из ответа TorrServer о её состоянии."""

from __future__ import annotations

from torrcast.adapters.torrserver.file_stats import file_stats
from torrcast.domain.torr_file import TorrFile


def test_files_are_read_with_their_ids_paths_and_lengths() -> None:
    """Каждый файл ответа становится файлом раздачи с теми же полями."""
    status = {"file_stats": [{"id": 1, "path": "a.mkv", "length": 10}, {"id": 2, "path": "b"}]}

    assert file_stats(status) == [TorrFile(1, "a.mkv", 10), TorrFile(2, "b", 0)]


def test_a_status_without_metadata_has_no_files() -> None:
    """Метаданных ещё нет - файлов нет, а не ошибка."""
    assert file_stats({}) == []
    assert file_stats({"file_stats": None}) == []


def test_entries_of_the_wrong_shape_are_skipped() -> None:
    """Чужая запись в списке не роняет разбор остальных."""
    assert file_stats({"file_stats": ["x", {"id": 3, "path": "c", "length": 5}]}) == [
        TorrFile(3, "c", 5)
    ]
