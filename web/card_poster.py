"""Обложка карточки: имя картинки только тогда, когда за ним есть байты.

Имя карточка считала всегда одной формулой (:func:`hass.poster_name.poster_name`), а
приговор о картинке (:class:`hass.hit_posters.HitPosters`) проходили только находки
поиска и полки. Стоило имени картины в круге разойтись с именем плитки («Usuzumizakura
Garo» против «Usuzumizakura GARO», замер на стенде `.104` 11-09-2026), и карточка
отдавала имя, на которое ``/api/poster`` отвечал 404: на месте обложки «нет обложки».
Здесь карточка проходит тот же приговор, но фоном: ответ им не задержан, а следующий
заход той же карточки уже знает итог.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import Final

from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from torrcast.domain.torrcast_error import TorrcastError

#: Сколько помнится промах: картинка у картины может появиться, но не за минуты, а
#: каждый заход карточки иначе снова звал бы приговор в сеть.
_MISS_TTL: Final = 600.0

Offer = Callable[[list[JsonValue]], list[JsonValue]]
Spawn = Callable[[Callable[[], None]], None]


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="card-poster").start()


class CardPoster:
    """Приговор обложки на картину: один поход в сеть на имя, итог в памяти процесса."""

    def __init__(
        self, offer: Offer, spawn: Spawn = _daemon, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self._offer = offer
        self._spawn = spawn
        self._clock = clock
        self._lock = threading.Lock()
        self._found: dict[str, str] = {}
        self._missed: dict[str, float] = {}
        self._asking: set[str] = set()

    def of(self, picture: Picture) -> tuple[str | None, bool]:
        """Имя картинки или ``None``, и второе - «приговор ещё идёт, спроси снова»."""
        record: JsonValue = {
            "title": picture.title,
            "year": picture.year,
            "kind": picture.kind,
            "original": picture.original or None,
        }
        key = picture.key
        with self._lock:
            if key in self._found:
                return self._found[key], False
            if self._clock() < self._missed.get(key, 0.0):
                return None, False
            fresh = key not in self._asking
            self._asking.add(key)
        if fresh:
            self._spawn(lambda: self._judge(key, record))
        with self._lock:
            return self._found.get(key), key in self._asking

    def _judge(self, key: str, record: JsonValue) -> None:
        """Отказ приговора - промах на срок, а не падение фонового потока."""
        name: str | None = None
        try:
            said = self._offer([record])
            first = said[0] if said else None
            if isinstance(first, dict) and isinstance(first.get("poster"), str):
                name = str(first["poster"])
        except (TorrcastError, OSError):
            name = None
        with self._lock:
            self._asking.discard(key)
            if name:
                self._found[key] = name
            else:
                self._missed[key] = self._clock() + _MISS_TTL


__all__ = ["CardPoster"]
