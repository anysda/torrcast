"""Путь к файлу состояния просмотра. Рядом с ним же лежит и недельный след.

Спрашивают его чтение и запись состояния и каталог ленты."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: Место состояния по умолчанию: каталог переменных данных службы, а не домашний.
#: Пишет его и команда, и юнит показа, поэтому дом у файла общий.
DEFAULT_STATE_PATH: Final = Path("/var/lib/torrcast/state.json")


def state_path() -> Path:
    """Путь к файлу состояния с учётом ``TORRCAST_STATE``."""
    return Path(os.environ.get("TORRCAST_STATE") or DEFAULT_STATE_PATH)
