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
from typing import Any

from torrcast.adapters.filesystem.state.shelves_cache_path import shelves_cache_path
from torrcast.adapters.filesystem.state.write_atomic import _write_atomic
from torrcast.domain.catalogs.tongue import EN, tongue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture_tile import picture_tile
from torrcast.domain.spoken_title import spoken_title
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_catalogue.torrent_catalogue import TorrentCatalogue
from torrcast.usecases.shelves.fresh_shelf import fresh_shelf
from torrcast.usecases.shelves.popular_shelf import popular_shelf

#: Кто приносит ленту последних раздач; в бою - :meth:`Prowlarr.feed`.
Feed = Callable[[int], list[FeedRow]]
#: Кто дописывает плиткам обложку; в бою - :data:`hass.hit_posters.hits`.offer.
Offer = Callable[[list[JsonValue]], list[JsonValue]]
#: Тот же ``Passport.of``: раздача сама латиницы не назвала - паспорт добирает её фоном
#: (:func:`web.related_lookup._seed` живёт тем же приёмом).
PassportOf = Callable[[str, bool, float], Origin]
#: Кто запускает фоновую сборку; в бою - настоящий поток-демон.
Spawn = Callable[[Callable[[], None]], None]
#: Потолок одного паспорта плитки - тот же, что и у родни (:data:`web.related_lookup.TIMEOUT`):
#: фон часовой, а не ответ человеку, и полторы секунды тут ничего не решают.
TIMEOUT = 8.0
#: Ключи, которые контракт ``GET /api/shelves`` разрешает плитке - и ни одного больше.
#: ``shown`` - имя ДЛЯ ЧЕЛОВЕКА (:func:`torrcast.domain.spoken_title.spoken_title`); ``title``
#: остаётся записанным именем ради ``query`` и полки обложек, которые считают по нему же.
_TILE_FIELDS: tuple[str, ...] = (
    "key",
    "title",
    "shown",
    "year",
    "kind",
    "quality",
    "poster",
    "query",
)


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: отдельный поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="shelves-cache").start()


def _no_passport(_title: str, _series: bool, _timeout: float) -> Origin:
    """Паспорт по умолчанию: без проводки плитка без своей латиницы остаётся записанной."""
    return Origin()


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
        """Собрать обе полки заново; отказ ленты не роняет цикл - следующий час свой."""
        try:
            rows = self.feed(self.limit)
            now = self.clock()
            body: dict[str, JsonValue] = {
                "fresh": self._tiles(fresh_shelf(rows, self.catalogue, now=now)),
                "popular": self._tiles(popular_shelf(rows, self.catalogue, now=now)),
                "built_at": now.isoformat(),
            }
        except TorrcastError:
            return
        with self._lock:
            self._body = body
        self._save(body)

    def _tiles(self, pictures: list[Any]) -> list[JsonValue]:
        """Плитки картин с предложенной обложкой, ужатые под контракт ``/api/shelves``."""
        seeds: list[JsonValue] = [picture_tile(picture) for picture in pictures]
        decorated = self.offer(seeds)
        return [self._project(record) for record in decorated]

    def _project(self, record: JsonValue) -> JsonValue:
        """Ровно поля контракта; розыскное ``original`` наружу не идёт, а ``shown``
        считается из него, пока он ещё на месте, либо из паспорта, если раздача своей
        латиницы не назвала (:mod:`torrcast.domain.picture_tile`)."""
        if not isinstance(record, dict):
            return record
        title, original = record.get("title"), record.get("original")
        shown = self._shown(title, original)
        return {
            field_name: shown if field_name == "shown" else record.get(field_name)
            for field_name in _TILE_FIELDS
        }

    def _shown(self, title: JsonValue, original: JsonValue) -> JsonValue:
        """Имя плитки для человека; неожиданная форма записи остаётся как есть.

        Паспорт зовётся только под английским языком: под русским латиница всё равно
        не покажется (:func:`torrcast.domain.spoken_title.spoken_title`), и звать
        Wikipedia ради ответа, который никто не прочитает, - шум, а не польза.
        """
        if not isinstance(title, str):
            return title
        latin = original if isinstance(original, str) and original else ""
        if not latin and tongue() == EN:
            latin = self._latin_of(title)
        return spoken_title(title, latin)

    def _latin_of(self, title: str) -> str:
        """Латиница из паспорта - раздача её не назвала, а Wikipedia может знать."""
        return self.passport(title, False, TIMEOUT).title

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
