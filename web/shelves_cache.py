"""Серверный кэш полок «Новинки»/«Популярное»: строится фоном, отдаётся мгновенно.

``GET /api/shelves`` не вправе ждать индексеры (TC-1110): человек открывает главный
экран, и полка, ждущая Prowlarr, - это то же самое зависшее меню, от которого круг
поиска ушёл врозь (:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`), только
на самом видном месте. До первой сборки полки честно пусты, это штатно, а не отказ.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import cast

from torrcast.adapters.filesystem.state.shelves_cache_path import shelves_cache_path
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT as SHELF_LIMIT
from web.build_shelf import build_shelf
from web.built_by_rule import FIELD, RULE
from web.drop_count import DropCount
from web.min_tiles import min_tiles
from web.read_shelves import read_shelves
from web.shelf_candidate import shelf_candidate
from web.shelf_tiles import Offer, PassportOf, Playable, _no_passport, _no_playable
from web.shelf_warm_targets import shelf_warm_targets
from web.warm_targets import WarmTarget
from web.write_shelves import write_shelves

#: Кто приносит ленту последних раздач; в бою - :meth:`Prowlarr.feed`.
Feed = Callable[[int], list[FeedRow]]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]
Warm = Callable[[list[WarmTarget], list[WarmTarget]], object]


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="shelves-cache").start()


def _no_warm(_targets: list[WarmTarget], _later: list[WarmTarget]) -> None:
    """Без проводки сборка не трогает очередь кругов."""


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
            self._pass()
            self.sleep(self.every)

    def _pass(self) -> None:
        """Одна пересборка; беда вне :class:`TorrcastError` роняет заход, а не поток.

        Поток фона один на процесс: умри он от чужого исключения (ошибка разбора,
        приговора, деления), полки застыли бы до рестарта молча.
        """
        try:
            self._rebuild()
        except Exception:
            traceback.print_exc()

    def _rebuild(self) -> None:
        """Собрать обе полки заново; отказ ленты не роняет цикл - следующий час свой.

        Молчащий индексер не приносит строк; фон склеивает добранную ленту по хэшу и
        берёт самую полную попытку. Добор останавливается без новых строк и роста полки.

        Готовая полка публикуется сразу, не дожидаясь соседней (:meth:`_publish`), и
        публикация - отдельный вопрос: даже самая полная попытка может оказаться хуже
        уже опубликованной (:func:`web.worth_publishing.worth_publishing`), и
        тогда фон отступает молча, до следующего часа.
        """
        with self._lock:
            origin = self._body
        if origin is None:
            origin = self._load()
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
                body: dict[str, JsonValue] = {FIELD: RULE, "built_at": now.isoformat()}
                for shelf in ("fresh", "popular"):
                    # Свой счётчик приговоров у каждой полки: планка массового отсева
                    # (:data:`web.worth_publishing.MASS_DROP`) меряет только её.
                    drops = DropCount()
                    tiles = build_shelf(
                        shelf,
                        list(rows.values()),
                        self.catalogue,
                        self.offer,
                        self.passport,
                        drops.wrap(self.playable),
                        now,
                    )
                    body[shelf] = tiles
                    self._publish(origin, shelf, tiles, now, drops)
            except TorrcastError:
                continue
            grew = best is None or min_tiles(body) > min_tiles(best)
            if grew:
                best = body
            if len(rows) == before and not grew:
                break
        if best is None:
            return

    def _publish(
        self,
        origin: dict[str, JsonValue],
        shelf: str,
        tiles: list[JsonValue],
        now: datetime,
        drops: DropCount,
    ) -> None:
        """Поставить готовую полку, не снимая строящуюся соседнюю (:mod:`web.shelf_candidate`)."""
        with self._lock:
            current = self._body if self._body is not None else origin
            complete = shelf == "popular"  # клеймо нового правила - по последней полке
            candidate = shelf_candidate(
                current, origin, shelf, tiles, drops, now=now, limit=SHELF_LIMIT, complete=complete
            )
            if candidate is None:
                return
        # Сначала факты плиток, затем публикация: видимый клик не ждёт поиска раздач.
        warmed = {shelf: cast(list[JsonValue], candidate[shelf])}
        self.warm(shelf_warm_targets(warmed), shelf_warm_targets(warmed, later=True))
        print(phrase("web.shelf.warmup_ordered", shelf=shelf, count=len(warmed[shelf])), flush=True)
        with self._lock:
            self._body = candidate
        print(phrase("web.shelf.published", shelf=shelf, count=len(warmed[shelf])), flush=True)
        write_shelves(self.path, candidate)

    def _load(self) -> dict[str, JsonValue]:
        return read_shelves(self.path)


__all__ = ["Feed", "Offer", "PassportOf", "Playable", "ShelvesCache", "Spawn", "Warm"]
