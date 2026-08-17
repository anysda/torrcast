"""Имя файла ленты за сутки: по нему её и находят все, кто ленту читает.

Зовут его писатель (:mod:`torrcast.adapters.filesystem.trace_journal.writer`), ротация и
чтение."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Final

from torrcast.adapters.filesystem.trace_journal.log_dir import log_dir

if TYPE_CHECKING:
    from pathlib import Path

#: Приставка и хвост имени файла ленты: по ним её узнают ротация (:func:`_prune`),
#: здоровье (:func:`health`) и чтение (:func:`records`). Между ними стоит день в виде
#: ``ГГГГММДД`` - только так даты сортируются хронологически как строки.
_PREFIX: Final = "trace-"
_SUFFIX: Final = ".jsonl"


def log_path(when: float | None = None) -> Path:
    """Файл ленты за сутки ``when`` (по умолчанию - сегодня). Ротация - по суткам."""
    day = time.strftime("%Y%m%d", time.localtime(when))
    return log_dir() / f"{_PREFIX}{day}{_SUFFIX}"
