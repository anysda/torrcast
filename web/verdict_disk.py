"""Вердикт «плитка играет» на диске: переживает рестарт, а не только процесс.

Круг раздач (:mod:`web.circle_disk`) уже живёт на диске тем же приёмом - строками,
которые переживают рестарт службы, а не только текущий процесс, - и вердикт
играбельности (:mod:`web.shelf_playable`) обязан тем же: часовая пересборка платит
секундами TorrServer за картину, и рестарт службы не вправе обнулять эту память.
Файл один, рядом с состоянием экземпляра, запись атомарная, размер ограничен - тот
же приём, что и у :class:`web.circle_disk.CircleDisk`.

«Не знаю» сюда никогда не попадает: вызывающий (:class:`web.shelf_playable.
ShelfPlayable`) передаёт только честные ``True``/``False`` - временное незнание не
факт про картину, и записывать его на диск означало бы застрять в нём до смены
правила.
"""

from __future__ import annotations

import contextlib
import json
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.torrcast_error import TorrcastError

#: Сколько картин помнит файл; старые вытесняются первыми (приём :data:`web.circle_disk.ENTRIES`).
ENTRIES: Final = 4000


def _file() -> Path:
    return state_path().with_name("shelf_verdicts.json")


@dataclass
class VerdictDisk:
    """Вердикт играбельности по ключу картины и правилу отбора; путь подставной в тестах."""

    path: Callable[[], Path] = _file
    _rows: dict[str, Any] | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(self, key: str, rule: int) -> bool | None:
        """Вердикт нынешнего правила, если он записан; чужое правило - как пустая запись."""
        with self._lock:
            entry = self._load().get(key)
        if not isinstance(entry, list) or len(entry) != 2:
            return None
        stored_rule, verdict = entry
        if stored_rule != rule or not isinstance(verdict, bool):
            return None
        return verdict

    def keep(self, key: str, rule: int, verdict: bool) -> None:
        """Записать честный вердикт правила; вызывающий отвечает, что это не «не знаю»."""
        with self._lock:
            rows = self._load()
            rows.pop(key, None)
            rows[key] = [rule, verdict]
            while len(rows) > ENTRIES:
                rows.pop(next(iter(rows)))
            # диск лёг - вердикт просто не переживёт рестарт, полке до этого дела нет
            with contextlib.suppress(TorrcastError):
                _write_atomic(self.path(), rows)

    def _load(self) -> dict[str, Any]:
        if self._rows is None:
            try:
                raw = json.loads(self.path().read_text(encoding="utf-8"))
            except (OSError, ValueError):
                raw = {}
            self._rows = raw if isinstance(raw, dict) else {}
        return self._rows


__all__ = ["ENTRIES", "VerdictDisk"]
