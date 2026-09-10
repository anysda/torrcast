"""Путь к файлу состояния просмотра. Рядом с ним же лежит и недельный след.

Спрашивают его чтение и запись состояния и каталог ленты."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

from torrcast.domain.instance_slug import DEFAULT_STATE, STATE_ENV

#: Место состояния по умолчанию: каталог переменных данных службы, а не домашний.
#: Пишет его и команда, и юнит показа, поэтому дом у файла общий. Само слово живёт в
#: :data:`torrcast.domain.instance_slug.DEFAULT_STATE`: по нему же экземпляр узнаёт боевой
#: путь и не метит свои имена суффиксом.
DEFAULT_STATE_PATH: Final = Path(DEFAULT_STATE)


def state_path() -> Path:
    """Путь к файлу состояния с учётом ``TORRCAST_STATE``."""
    return Path(os.environ.get(STATE_ENV) or DEFAULT_STATE_PATH)
