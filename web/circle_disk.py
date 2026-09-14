"""Круги раздач на диске на сутки: после перезапуска повтор запроса не ждёт индексеры.

Хранится не набор планов, а то, что сказал каталог (:mod:`torrcast.usecases.discover.
told_indexer`): строки - простые данные и переживают смену версии, а круг по ним
собирается заново текущим кодом. Приём «отдать сохранённое, освежить фоном» - по образцу
Torrentio (``addon/lib/cache.js``, Apache-2.0, github.com/TheBeastLT/torrentio-scraper).
Файл один, рядом с состоянием экземпляра, запись атомарная, размер ограничен.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.raw_result import RawResult
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.usecases.discover.told_indexer import Told

#: Сколько живёт круг на диске.
DAY: Final = 86400.0
#: Сколько запросов помнит файл; старые уходят первыми.
ENTRIES: Final = 200
#: Потолок файла в байтах: круг «матрицы» - около 60 КБ.
BYTES: Final = 4_000_000


def _file() -> Path:
    return state_path().with_name("circles.json")


@dataclass
class CircleDisk:
    """Запись кругов по ключу запроса; часы и путь подставные ради тестов."""

    path: Callable[[], Path] = _file
    clock: Callable[[], float] = time.time
    ttl: float = DAY
    _rows: dict[str, Any] | None = field(default=None, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def told(self, key: str) -> list[Told] | None:
        """Запись круга не старше :attr:`ttl`, иначе ``None``."""
        with self._lock:
            entry = self._load().get(key)
        if not isinstance(entry, dict) or entry.get("at", 0) + self.ttl <= self.clock():
            return None
        try:
            return [_said(said) for said in entry["told"]]
        except (KeyError, TypeError, ValueError):
            return None

    def keep(self, key: str, told: list[Told]) -> None:
        """Записать круг; лишнее по счёту и по байтам вытесняется от старых."""
        entry = {"at": self.clock(), "told": [_row(said) for said in told]}
        with self._lock:
            rows = self._load()
            rows.pop(key, None)
            rows[key] = entry
            while len(rows) > 1 and (
                len(rows) > ENTRIES or len(json.dumps(rows, ensure_ascii=False)) > BYTES
            ):
                rows.pop(min(rows, key=lambda name: rows[name].get("at", 0)))
            # диск лёг - круги просто не переживут перезапуск, поиску до этого дела нет
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


def _row(said: Told) -> list[Any]:
    kind, query, spare, capped, rows = said
    return [kind, query, spare, list(capped), [_raw(row) for row in rows]]


def _raw(row: RawResult) -> list[Any]:
    fields = (row.title, row.info_hash, row.size, row.seeders, row.indexer, row.copies)
    return [*fields, list(row.indexers), list(row.names)]


def _said(row: list[Any]) -> Told:
    kind, query, spare, capped, rows = row
    return (str(kind), str(query), float(spare), tuple(capped), [_back(one) for one in rows])


def _back(one: list[Any]) -> RawResult:
    title, info_hash, size, seeders, indexer, copies, indexers, names = one
    return RawResult(
        str(title), str(info_hash), int(size), int(seeders), str(indexer), int(copies),
        tuple(indexers), tuple(names),
    )  # fmt: skip


__all__ = ["BYTES", "DAY", "ENTRIES", "CircleDisk"]
