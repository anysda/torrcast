"""Путь к файлу настроек. Обязателен в нём только адрес приёмника.

Спрашивают его чтение настроек, список написанных ключей и запись."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: Место настроек по умолчанию: общесистемный каталог, потому что читает их и юнит показа.
DEFAULT_CONFIG_PATH: Final = Path("/etc/torrcast/config.json")


def config_path() -> Path:
    """Путь к конфигу с учётом ``TORRCAST_CONFIG``."""
    return Path(os.environ.get("TORRCAST_CONFIG") or DEFAULT_CONFIG_PATH)
