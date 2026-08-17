"""Каталог недельной ленты: рядом с состоянием либо там, куда его увели окружением.

Спрашивают его имя файла (:func:`log_path`), здоровье ленты и чтение записей."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: Переопределение каталога ленты (тесты, локальный запуск). Пусто - рядом с состоянием.
LOG_ENV: Final = "TORRCAST_LOG"


def log_dir() -> Path:
    """Каталог ленты: ``TORRCAST_LOG`` или каталог файла состояния."""
    override = os.environ.get(LOG_ENV)
    if override:
        return Path(override)
    from torrcast.adapters.filesystem.state import state_path

    return state_path().parent
