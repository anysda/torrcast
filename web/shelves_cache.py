"""Серверный кэш полок «Новинки»/«Популярное»: строится фоном, отдаётся мгновенно.

``GET /api/shelves`` не вправе ждать индексеры (TC-1110): человек открывает главный
экран, и полка, ждущая Prowlarr, - это то же самое зависшее меню, от которого круг
поиска ушёл врозь (:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`), только
на самом видном месте страницы. Первый заход после установки честно пуст - фон ещё не
успел ни разу собрать полки, - и это штатное состояние, а не отказ.
"""

from __future__ import annotations

import contextlib
import json
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from torrcast.adapters.filesystem.state.shelves_cache_path import shelves_cache_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT as SHELF_LIMIT
from torrcast.usecases.shelves.fresh_shelf import fresh_shelf
from torrcast.usecases.shelves.popular_shelf import popular_shelf
from web.min_tiles import FLOOR, min_tiles
from web.shelf_tiles import Offer, PassportOf, _no_passport, shelf_tiles

#: Кто приносит ленту последних раздач; в бою - :meth:`Prowlarr.feed`.
Feed = Callable[[int], list[FeedRow]]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]
#: Сколько кандидатов собирается на полку сверх видимых плиток: картины без обложки
#: на полку не попадают, а их места добираются следующими картинами с обложкой
#: (:func:`web.shelf_tiles._covered`), и запас кандидатов - это из чего добирать.
_CANDIDATES: Final = SHELF_LIMIT * 3


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="shelves-cache").start()


@dataclass
class ShelvesCache:
    """Полки в памяти и на диске: обновляет их фон раз в час, читает - каждый запрос.

    Фон, сон и часы - подставные ради тестов (:mod:`tests.thread_guard` роняет тест,
    следующий за тем, что оставил настоящий поток жить): подделка зовёт ``spawn`` и
    ``sleep`` синхронно, ни разу не открывая настоящий сокет.
    """

    feed: Feed
    catalogue: TorrentCatalogue
    offer: Offer
    path: Path = field(default_factory=shelves_cache_path)
    limit: int = 300
    every: float = 3600.0
    #: Сколько заходов добора делает одна сборка, пока полки короче планки ТЗ §9
    #: (:data:`web.min_tiles.FLOOR`), и пауза между заходами.
    attempts: int = 3
    retry_pause: float = 10.0
    passport: PassportOf = _no_passport
    spawn: Spawn = _daemon
    sleep: Callable[[float], None] = time.sleep
    clock: Callable[[], datetime] = lambda: datetime.now(UTC)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _body: dict[str, JsonValue] | None = field(default=None, repr=False, compare=False)
    _started: bool = field(default=False, repr=False, compare=False)

    def get(self) -> dict[str, JsonValue]:
        """Тело ответа сразу: из памяти, а не с ним - с диска, а нет и там - пустые полки."""
        self._ensure_started()
        with self._lock:
            if self._body is not None:
                return self._body
        loaded = self._load()
        with self._lock:
            if self._body is None:
                self._body = loaded
            return self._body

    def _ensure_started(self) -> None:
        """Фон встаёт один раз, при первом же обращении - не при создании предмета."""
        with self._lock:
            if self._started:
                return
            self._started = True
        self.spawn(self._loop)

    def _loop(self) -> None:
        while True:
            self._rebuild()
            self.sleep(self.every)

    def _rebuild(self) -> None:
        """Собрать обе полки заново; отказ ленты не роняет цикл - следующий час свой.

        Медленный круг отдаёт не всю ленту (молчащий индексер не приносит строк), и
        сборка выходит короче планки ТЗ §9 (:data:`web.min_tiles.FLOOR`). Такую
        полку человеку не отдают: фон добирает ленту ещё заходами, склеивая строки по
        хэшу раздачи, и берёт самую полную из попыток; а собранную полную полку
        короткая сборка не заменяет вовсе. Тем же счётом меряется и отбор плиток без
        обложки: полка после него не вправе стать короче, чем была бы без него.
        """
        rows: dict[str, FeedRow] = {}
        best: dict[str, JsonValue] | None = None
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(self.retry_pause)
            try:
                for row in self.feed(self.limit):
                    rows.setdefault(row.raw.info_hash.lower(), row)
                body = self._build(list(rows.values()))
            except TorrcastError:
                continue
            if best is None or min_tiles(body) > min_tiles(best):
                best = body
            if min_tiles(best) >= FLOOR:
                break
        if best is None:
            return
        with self._lock:
            current = self._body
            if current is not None and min_tiles(current) >= FLOOR > min_tiles(best):
                return
            self._body = best
        self._save(best)

    def _build(self, rows: list[FeedRow]) -> dict[str, JsonValue]:
        """Тело ответа из строк ленты: обе полки и отметка времени сборки."""
        now = self.clock()
        return {
            "fresh": self._tiles(fresh_shelf(rows, self.catalogue, now=now, limit=_CANDIDATES)),
            "popular": self._tiles(popular_shelf(rows, self.catalogue, now=now, limit=_CANDIDATES)),
            "built_at": now.isoformat(),
        }

    def _tiles(self, pictures: list[Any]) -> list[JsonValue]:
        """Видимые плитки полки: только картины с обложкой, в числе видимых ТЗ §9."""
        return shelf_tiles(pictures, self.offer, self.passport, limit=SHELF_LIMIT)

    def _load(self) -> dict[str, JsonValue]:
        try:
            raw: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty()
        return raw if isinstance(raw, dict) else _empty()

    def _save(self, body: dict[str, JsonValue]) -> None:
        # диск лёг - полки просто не переживут рестарт, показу до этого дела нет
        with contextlib.suppress(TorrcastError):
            _write_atomic(self.path, body)


def _empty() -> dict[str, JsonValue]:
    """Полки до первой сборки: пустой список, а не выдуманная картина."""
    return {"fresh": [], "popular": [], "built_at": None}


__all__ = ["Feed", "Offer", "PassportOf", "ShelvesCache", "Spawn"]
