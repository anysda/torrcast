"""Плитки полки перед кликом: сведения до публикации, родня своей картины после круга.

Прогрев кругов (:mod:`web.warm_cache`) знает только запросы. Полке же нужно больше:
описание и родня плитки должны ждать человека раньше, чем единственный фоновый круг
доберётся до её раздач. Круг поиска может поставить плитку не первой, поэтому ключ
плитки запоминается при заказе и родня берётся её картины, а не первой в круге.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final

if TYPE_CHECKING:
    from torrcast.usecases.facts import FactPicture
    from torrcast.usecases.select.plan import Plan

#: Плитка полки: запрос круга, ключ картины, название, год, вид.
WarmTarget = tuple[str, str, str, int | None, str]
Circle = Callable[[str], "list[Plan]"]
Pictures = Callable[["list[FactPicture]"], None]
Kin = Callable[["FactPicture"], None]
Ask = Callable[[Sequence[str]], int]
Spawn = Callable[[Callable[[], None]], None]
#: One hovered tile may use the background sources. A wider fan-out left the opened
#: card competing with eight passports and two overlapping Wikipedia batches.
RELATED_LIMIT: Final = 1


def _no_ask(_screen: Sequence[str]) -> int:
    """Без проводки заказ плиток кругов не ставит."""
    return 0


def _daemon(job: Callable[[], None]) -> None:
    """Тестовый заказ плиток без проводки не оставляет настоящий поток жить."""
    threading.Thread(target=job, daemon=True, name="warm-targets").start()


@dataclass
class WarmTargets:
    """Обёртка круга и заказ плиток полки; боевых собирает :mod:`web.warm_wiring`."""

    circle: Circle
    prime: Pictures
    kin: Kin
    background_kin: Kin | None = None
    ask: Ask = _no_ask
    spawn: Spawn = _daemon
    _keys: dict[str, str] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    _kin_queue: list[FactPicture] = field(default_factory=list, repr=False)
    _kin_active: FactPicture | None = field(default=None, repr=False)
    _kin_running: bool = field(default=False, repr=False)

    def search(self, query: str) -> list[Plan]:
        """Круг как есть, и вслед родня картины, ради которой его заказали."""
        try:
            plans = self.circle(query)
        finally:
            with self._lock:
                key = self._keys.pop(query.strip(), "")
        if plans:
            picture = next(
                (plan.picture for plan in plans if plan.picture.key == key), plans[0].picture
            )
            self.kin((picture.title, picture.year, picture.kind))
        return plans

    def prepare(self, targets: Sequence[WarmTarget]) -> int:
        """Start facts for the first tile, then queue its indexer circles."""
        pictures: list[FactPicture] = [
            (title, year, kind) for _query, _key, title, year, kind in targets
        ]
        self.prime(pictures[:RELATED_LIMIT])
        with self._lock:
            self._keys.update({query.strip(): key for query, key, *_rest in targets})
        return self.ask([query for query, *_rest in targets])

    def observe(self, targets: Sequence[WarmTarget], source: bool = True) -> int:
        """Начать справку и родню видимых плиток, не держа ответ ``seen``.

        Круги по их запросам всё ещё идут обычной очередью экрана. Факты и родня
        независимы от индексеров, поэтому им не надо ждать этот круг и клик получает
        их после наведения, а не после 5-9 секунд поиска раздач.
        """
        pictures: list[FactPicture] = [
            (title, year, kind)
            for _query, _key, title, year, kind in targets
            if title and year is not None and kind in {"movie", "tv"}
        ]
        if pictures and source:
            # `warm.js` moves the hovered tile first. Leave source capacity for the
            # facts and related shelf of the card which is about to open.
            for picture in pictures[:RELATED_LIMIT]:
                self.kin(picture)
            self.spawn(lambda: self.prime(pictures[:RELATED_LIMIT]))
        elif pictures:
            self._queue_kin(pictures)
        with self._lock:
            self._keys.update({query.strip(): key for query, key, *_rest in targets})
        return self.ask([query for query, *_rest in targets])

    def _queue_kin(self, pictures: Sequence[FactPicture]) -> None:
        """Keep visible franchise work in one lane, replacing an old off-screen tail.

        A visible shelf has eight tiles. Its passport can make two parallel Wikipedia
        calls; a hovered card's blurb makes three. Six concurrent calls receive 429
        from Wikipedia on CT501, so the visible lane has exactly one active item.
        """
        wanted: list[FactPicture] = []
        for picture in pictures[:8]:
            if picture not in wanted and picture != self._kin_active:
                wanted.append(picture)
        with self._lock:
            self._kin_queue = wanted
            if self._kin_running or not wanted:
                return
            self._kin_running = True
        self.spawn(self._pump_kin)

    def _pump_kin(self) -> None:
        """Run one visible passport/franchise build at a time outside the HTTP handler."""
        while True:
            with self._lock:
                if not self._kin_queue:
                    self._kin_running = False
                    return
                picture = self._kin_queue.pop(0)
                self._kin_active = picture
            try:
                (self.background_kin or self.kin)(picture)
            finally:
                with self._lock:
                    self._kin_active = None


__all__ = ["WarmTarget", "WarmTargets"]
