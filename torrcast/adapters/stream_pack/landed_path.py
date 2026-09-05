"""Называет путь файла настоящего места старта; по нему CLI сверяет запасной путь ожидания."""

from __future__ import annotations

from pathlib import Path
from typing import Final

#: Лежит рядом с флажком картинки (:data:`torrcast.domain.hls_settings.PLAYING_FLAG`):
#: тот же каталог, тот же старый способ показу сказать что-то своему CLI - файлом
#: на общем диске, других путей между двумя процессами нет.
LANDED_FILE: Final = "landed.at"


def landed_path(out: Path) -> Path:
    """Путь файла настоящего места старта (:data:`LANDED_FILE`)."""
    return out / LANDED_FILE
