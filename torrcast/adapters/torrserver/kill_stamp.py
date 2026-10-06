"""Когда службу раздач в последний раз убил продукт: отметка общая для всех его процессов.

Подъём службы (:mod:`.engine_restart`) не убивает её чаще раза в ``PAUSE``. Помнить это в
памяти процесса мало: мост и каждый показ - отдельные процессы, и показ, начатый после
KILL из моста, о нём не знал и убивал службу снова (стенд: KILL моста, через шесть минут
KILL нового показа на том же зависе). Отметка лежит файлом рядом с состоянием просмотра и
пишется атомарно: читатель в соседнем процессе видит старую отметку или новую, а не пустой
файл, который снял бы паузу.
"""

from __future__ import annotations

import json
from pathlib import Path

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.torrcast_error import TorrcastError

NAME = "engine-killed"


class KillStamp:
    """Стенное время последнего KILL службы раздач; нет файла или он битый - не убивали."""

    def __init__(self, path: Path | None = None) -> None:
        self._path = path

    def at(self) -> float | None:
        try:
            return float(json.loads(self._where().read_text(encoding="utf-8"))["at"])
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def mark(self, wall: float) -> None:
        """Запомнить KILL; не записалось - пауза держится хотя бы в этом процессе."""
        try:
            _write_atomic(self._where(), {"at": round(wall, 3)}, durable=False)
        except (OSError, TorrcastError):
            return

    def _where(self) -> Path:
        return self._path or state_path().with_name(NAME)


__all__ = ["KillStamp"]
