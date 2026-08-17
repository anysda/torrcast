"""Какие настройки написаны в файле на самом деле, в отличие от умолчаний.

Спрашивает их след: по одному значению файл от умолчания задним числом не отличить."""

from __future__ import annotations

import json
from typing import Any

from torrcast.adapters.filesystem.state.config_path import config_path
from torrcast.domain.config import Config


def config_keys() -> frozenset[str]:
    """Ключи, действительно написанные в JSON, в отличие от умолчаний :class:`Config`.

    Вызывается после :func:`load_config`, поэтому повторная короткая читка не вводит
    второй способ разбирать настройки. Она нужна следу: одинаковое число может прийти
    из файла стенда или из умолчания, а задним числом по одному значению их не отличить.
    """
    path = config_path()
    if not path.exists():
        return frozenset()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(raw, dict):
        return frozenset()
    return frozenset(key for key in raw if key in Config.__dataclass_fields__)
