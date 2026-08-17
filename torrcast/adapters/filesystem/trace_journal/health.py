"""Здоровье самой ленты по ``stat``, без разбора содержимого.

Спрашивает его щуп машины для строки ``cast doctor``."""

from __future__ import annotations

import contextlib

from torrcast.adapters.filesystem.trace_journal.log_dir import log_dir
from torrcast.adapters.filesystem.trace_journal.log_path import _PREFIX, _SUFFIX


def health() -> tuple[bool, float, int]:
    """Здоровье самой ленты: есть ли она, когда писали последний раз, сколько весит.

    Возвращает ``(есть, время последней записи, байт всего)``; время - ``0.0``, если
    ленты нет. Файлы читаются по ``stat``, содержимое не разбирается: строка в
    ``cast doctor`` отвечает на «пишется ли след», а не «что в нём».
    """
    newest, total, found = 0.0, 0, False
    with contextlib.suppress(OSError):
        for path in log_dir().glob(f"{_PREFIX}*{_SUFFIX}"):
            with contextlib.suppress(OSError):
                stat = path.stat()
                found = True
                total += stat.st_size
                newest = max(newest, stat.st_mtime)
    return found, newest, total
