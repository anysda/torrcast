"""Серверный кэш полок, строящийся фоном и мгновенно отвечающий на ``GET /api/shelves``."""

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
from web._stale_tiles import _keep_stale_tiles
from web.built_by_rule import FIELD, RULE
from web.drop_count import DropCount
from web.min_tiles import min_tiles
from web.shelf_tiles import Offer, PassportOf, Playable, _no_passport, _no_playable, shelf_tiles
from web.shelf_warm_targets import shelf_warm_targets
from web.warm_targets import WarmTarget
from web.worth_publishing import worth_publishing

#: Кто приносит ленту последних раздач; в бою - :meth:`Prowlarr.feed`.
Feed = Callable[[int], list[FeedRow]]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]
Warm = Callable[[list[WarmTarget], list[WarmTarget]], object]
_CANDIDATES: Final = SHELF_LIMIT * 3


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="shelves-cache").start()


def _no_warm(_targets: list[WarmTarget], _later: list[WarmTarget]) -> None:
    """Без проводки сборка не трогает очередь кругов."""


@dataclass
class ShelvesCache:
    """Полки в памяти и на диске: фон обновляет, запрос только читает."""

    feed: Feed
    catalogue: TorrentCatalogue
    offer: Offer
    path: Path = field(default_factory=shelves_cache_path)
    limit: int = 300
    every: float = 3600.0
    #: Потолок заходов добора ленты (:meth:`_rebuild` бросает раньше, если заход не
    #: принёс ни новых строк, ни полки полнее прежнего захода), и их пауза.
    attempts: int = 3
    retry_pause: float = 10.0
    passport: PassportOf = _no_passport
    playable: Playable = _no_playable
    warm: Warm = _no_warm
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
        """Собрать полки, публикуя готовую до постройки соседней."""
        rows: dict[str, FeedRow] = {}
        best: dict[str, JsonValue] | None = None
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(self.retry_pause)
            before = len(rows)
            try:
                for row in self.feed(self.limit):
                    rows.setdefault(row.raw.info_hash.lower(), row)
                now = self.clock()
                fresh_drops = DropCount()
                fresh = self._build_shelf(
                    "fresh", list(rows.values()), fresh_drops.wrap(self.playable), now
                )
                self._publish("fresh", fresh, now, fresh_drops)
                popular_drops = DropCount()
                popular = self._build_shelf(
                    "popular", list(rows.values()), popular_drops.wrap(self.playable), now
                )
                body: dict[str, JsonValue] = {
                    FIELD: RULE,
                    "fresh": fresh,
                    "popular": popular,
                    "built_at": now.isoformat(),
                }
            except TorrcastError:
                continue
            self._publish("popular", popular, now, popular_drops, complete=True)
            grew = best is None or min_tiles(body) > min_tiles(best)
            if grew:
                best = body
            if len(rows) == before and not grew:
                break
        if best is None:
            return
        # Готовая полка не ждёт ни соседнюю, ни проводку первого клика.
        self.warm(shelf_warm_targets(best), shelf_warm_targets(best, later=True))

    def _build_shelf(
        self, shelf: str, rows: list[FeedRow], playable: Playable, now: datetime
    ) -> list[JsonValue]:
        """Плитки одной полки из строк ленты, с отдельным счётчиком приговоров."""
        pictures = (
            fresh_shelf(rows, self.catalogue, now=now, limit=_CANDIDATES)
            if shelf == "fresh"
            else popular_shelf(rows, self.catalogue, now=now, limit=_CANDIDATES)
        )
        return self._tiles(pictures, playable)

    def _publish(
        self,
        shelf: str,
        tiles: list[JsonValue],
        now: datetime,
        drops: DropCount,
        *,
        complete: bool = False,
    ) -> None:
        """Поставить готовую полку, не снимая ещё строящуюся соседнюю.

        Клеймо меняется после второй полки, поэтому новое короче не спорит со старым.
        """
        with self._lock:
            current = self._body or _empty()
            candidate = {
                **current,
                shelf: _keep_stale_tiles(current, shelf, tiles, drops),
                "built_at": now.isoformat(),
            }
            if complete:
                candidate[FIELD] = RULE
            if not worth_publishing(current, candidate, drops):
                return
            self._body = candidate
        self._save(candidate)

    def _tiles(self, pictures: list[Any], playable: Playable) -> list[JsonValue]:
        """Видимые плитки полки: только картины с обложкой, в числе видимых ТЗ §9."""
        return shelf_tiles(pictures, self.offer, self.passport, playable, limit=SHELF_LIMIT)

    def _load(self) -> dict[str, JsonValue]:
        try:
            raw: Any = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return _empty()
        # Клеймо велит пересобрать, но прежнее или бесклейменное тело остаётся экраном.
        return raw if isinstance(raw, dict) else _empty()

    def _save(self, body: dict[str, JsonValue]) -> None:
        # диск лёг - полки просто не переживут рестарт, показу до этого дела нет
        with contextlib.suppress(TorrcastError):
            _write_atomic(self.path, body)


def _empty() -> dict[str, JsonValue]:
    """Полки до первой сборки: пустой список, а не выдуманная картина."""
    return {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}


__all__ = ["Feed", "Offer", "PassportOf", "Playable", "ShelvesCache", "Spawn", "Warm"]
