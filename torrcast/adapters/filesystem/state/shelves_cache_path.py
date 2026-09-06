"""Путь к файлу кэша полок «Новинки»/«Популярное». Переживает рестарт службы."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Final

#: Место кэша по умолчанию: рядом с состоянием показа, тот же общий каталог службы.
DEFAULT_SHELVES_CACHE_PATH: Final = Path("/var/lib/torrcast/shelves.json")


def shelves_cache_path() -> Path:
    """Путь к кэшу полок с учётом ``TORRCAST_SHELVES_CACHE``."""
    return Path(os.environ.get("TORRCAST_SHELVES_CACHE") or DEFAULT_SHELVES_CACHE_PATH)


__all__ = ["DEFAULT_SHELVES_CACHE_PATH", "shelves_cache_path"]
