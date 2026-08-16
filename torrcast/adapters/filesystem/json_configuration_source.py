"""Читает настройки сценариев из JSON-файла и окружения."""

from __future__ import annotations

import json
import os
from collections.abc import Mapping
from dataclasses import fields
from pathlib import Path
from typing import Any

from torrcast.domain.settings import Settings

DEFAULT_CONFIG_PATH = Path("/etc/torrcast/config.json")


class JsonConfigurationSource:
    """Источник настроек с прежним путём и переменной ``TORRCAST_CONFIG``."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def load(self) -> Settings:
        path = Path(self._environ.get("TORRCAST_CONFIG") or DEFAULT_CONFIG_PATH)
        try:
            raw: Any = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            raw = {}
        if not isinstance(raw, dict):
            raise ValueError("конфиг должен быть JSON-объектом")
        known = {item.name for item in fields(Settings)}
        return Settings(**{key: value for key, value in raw.items() if key in known})
