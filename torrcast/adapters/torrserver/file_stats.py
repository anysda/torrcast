"""Файлы раздачи из ответа TorrServer о её состоянии."""

from typing import Any

from torrcast.domain.torr_file import TorrFile


def file_stats(status: dict[str, Any]) -> list[TorrFile]:
    """Список файлов раздачи; метаданных ещё нет или ответ не того вида - пусто."""
    raw = status.get("file_stats")
    if not isinstance(raw, list):
        return []
    return [
        TorrFile(int(i.get("id") or 0), str(i.get("path", "")), int(i.get("length") or 0))
        for i in raw
        if isinstance(i, dict)
    ]
