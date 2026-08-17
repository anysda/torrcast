"""Чтение настроек с диска: отсутствующий файл - это умолчания, а не беда.

Зовут его корень запуска и щупы; битый файл здесь и превращается в понятную ошибку."""

from __future__ import annotations

import json
from typing import Any

from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.domain.config import Config
from torrcast.domain.torrcast_error import TorrcastError


def load_config() -> Config:
    """Прочитать конфиг; отсутствующий файл — не ошибка, а дефолты."""
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TorrcastError(f"битый конфиг {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TorrcastError(f"битый конфиг {path}: ожидался объект JSON")
    return Config.from_json(raw)
