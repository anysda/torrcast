"""Серверный кэш полок «Новинки»/«Популярное»: строится фоном, отдаётся мгновенно.

``GET /api/shelves`` не вправе ждать индексеры (TC-1110): человек открывает главный
экран, и полка, ждущая Prowlarr, - это то же самое зависшее меню, от которого круг
поиска ушёл врозь (:meth:`torrcast.adapters.prowlarr.prowlarr.Prowlarr._apart`), только
на самом видном месте страницы. Первый заход после установки честно пуст - фон ещё не
успел ни разу собрать полки, - и это штатное состояние, а не отказ.
"""

from __future__ import annotations

import threading
import time
import traceback
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from torrcast.adapters.filesystem.state.shelves_cache_path import shelves_cache_path
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import LIMIT as SHELF_LIMIT
from web.cold import cold
from web.drop_count import DropCount
from web.min_tiles import min_tiles
from web.publish_shelf import Warm, publish_shelf
from web.read_shelves import read_shelves
from web.shelf_pass import ShelfPass
from web.shelf_tiles import Offer, PassportOf, Playable, _no_passport, _no_playable

#: Кто приносит ленту последних раздач; в бою - :meth:`Prowlarr.feed`.
Feed = Callable[[int], list[FeedRow]]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="shelves-cache").start()


def _no_warm(_targets: object, _later: object) -> None:
    """Без проводки сборка не трогает очередь кругов."""


@dataclass
class ShelvesCache:
    """Полки в памяти и на диске: обновляет их фон раз в час, читает - каждый запрос.

    Фон, сон и часы подставные ради тестов (:mod:`tests.thread_guard` роняет тест после
    живого потока): подделка зовёт ``spawn`` и ``sleep`` синхронно, без сокета.
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
    #: Холодный показ до приговоров (:mod:`web.shelf_pass`): ``ask`` спрашивает обложки не
    #: дожидаясь байтов, ``landed`` - записи с уже легшими, ``arriving`` - едет ли ещё чья-то.
    ask: Offer | None = None
    landed: Offer = lambda records: records
    arriving: Callable[[list[JsonValue]], bool] = lambda _records: False
    workers: int = 1
    early: bool = False
    filling: bool = field(default=False, repr=False, compare=False)
    settling: bool = field(default=False, repr=False, compare=False)
    _origin: dict[str, JsonValue] = field(default_factory=dict, repr=False, compare=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)
    _body: dict[str, JsonValue] | None = field(default=None, repr=False, compare=False)
    _started: bool = field(default=False, repr=False, compare=False)

    def get(self) -> dict[str, JsonValue]:
        """Тело ответа сразу: из памяти, а не с ним - с диска, а нет и там - пустые полки."""
        self.start()
        with self._lock:
            if self._body is not None:
                return self._body
        loaded = self._load()
        with self._lock:
            if self._body is None:
                self._body = loaded
            return self._body

    def start(self) -> None:
        """Фон встаёт один раз; холодное тело (:mod:`web.cold`) метит ответ сборкой сразу."""
        with self._lock:
            if self._started:
                return
            self._started = True
        self.filling = self.settling = self.early and cold(self._body or self._load())
        self.spawn(self._loop)

    def _loop(self) -> None:
        while True:
            self._pass()
            self.sleep(self.every)

    def _pass(self) -> None:
        """Одна пересборка; беда вне :class:`TorrcastError` роняет заход, а не поток:
        он один на процесс, и умри он от чужого исключения, полки застыли бы молча."""
        try:
            self._rebuild()
        except Exception:
            traceback.print_exc()
        finally:  # a feed that never answered must not leave the counter on
            self.filling = self.settling = False

    def _rebuild(self) -> None:
        """Собрать обе полки заново; отказ ленты не роняет цикл - следующий час свой.

        Молчащий индексер не приносит строк, и сборка выходит короче, чем могла бы: фон
        добирает ленту ещё заходами, склеивая строки по хэшу раздачи. Добор встаёт САМ:
        заход без новых строк и без более полной полки следующего добавить не может.
        Пока лента недосчитана (:class:`torrcast.domain.feed_rows.FeedRows`), счётчик
        страницы горит и через паузу. Готовая полка публикуется сразу (:meth:`publish`),
        но и самая полная попытка может оказаться хуже уже опубликованной
        (:func:`web.worth_publishing.worth_publishing`) - тогда фон отступает до часа.
        """
        with self._lock:
            origin = self._body
        if origin is None:
            origin = self._load()
        self._origin = origin
        rows: dict[str, FeedRow] = {}
        best: dict[str, JsonValue] | None = None
        for attempt in range(self.attempts):
            if attempt:
                self.sleep(self.retry_pause)
            before = len(rows)
            try:
                fetched = self.feed(self.limit)
                for row in fetched:
                    rows.setdefault(row.raw.info_hash.lower(), row)
                with self._lock:
                    current = self._body if self._body is not None else origin
                more = attempt + 1 < self.attempts and getattr(fetched, "missed", 0) > 0
                body = ShelfPass(self, list(rows.values()), self.clock(), current, more=more).run()
            except TorrcastError:
                continue
            grew = best is None or min_tiles(body) > min_tiles(best)
            if grew:
                best = body
            if len(rows) == before and not grew:
                break

    def publish(
        self,
        shelf: str,
        tiles: list[JsonValue],
        drops: DropCount,
        now: datetime,
        complete: bool,
        unstamped: bool = False,
    ) -> None:
        """Поставить полку, не снимая соседнюю (:mod:`web.shelf_candidate`)."""
        with self._lock:
            current = self._body if self._body is not None else self._origin
        publish_shelf(
            current,
            self._origin,
            shelf,
            tiles,
            drops,
            now=now,
            limit=SHELF_LIMIT,
            warm=self.warm,
            store=self._store,
            path=self.path,
            complete=complete,
            unstamped=unstamped,
        )

    def _store(self, body: dict[str, JsonValue]) -> None:
        with self._lock:
            self._body = body

    def _load(self) -> dict[str, JsonValue]:
        return read_shelves(self.path)


__all__ = ["Feed", "Offer", "PassportOf", "Playable", "ShelvesCache", "Spawn", "Warm"]
