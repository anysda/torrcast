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
#: Паспорта видимой полки - один Wikipedia-поход до наведения. Восемь плиток уже
#: приходят в один экран; их Q-id позволяет полке открытой карточки идти сразу в Wikidata.
PASSPORT_LIMIT: Final = 8


def _no_ask(_screen: Sequence[str]) -> int:
    """Без проводки заказ плиток кругов не ставит."""
    return 0


def _no_kin(_picture: FactPicture) -> None:
    """Тестовый прогрев может не иметь проводки паспортов."""
    return None


def _daemon(job: Callable[[], None]) -> None:
    """Тестовый заказ плиток без проводки не оставляет настоящий поток жить."""
    threading.Thread(target=job, daemon=True, name="warm-targets").start()


@dataclass
class WarmTargets:
    """Обёртка круга и заказ плиток полки; боевых собирает :mod:`web.warm_wiring`."""

    circle: Circle
    prime: Pictures
    kin: Kin
    passport: Kin = _no_kin
    ask: Ask = _no_ask
    spawn: Spawn = _daemon
    _keys: dict[str, str] = field(default_factory=dict, repr=False)
    _passports: list[FactPicture] = field(default_factory=list, repr=False)
    _passport_running: bool = field(default=False, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

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
        self._queue_passports(pictures)
        if pictures and source:
            # `warm.js` moves the hovered tile first. Leave source capacity for the
            # facts and related shelf of the card which is about to open.
            for picture in pictures[:RELATED_LIMIT]:
                self.kin(picture)
            self.spawn(lambda: self.prime(pictures[:RELATED_LIMIT]))
        with self._lock:
            self._keys.update({query.strip(): key for query, key, *_rest in targets})
        return self.ask([query for query, *_rest in targets])

    def _queue_passports(self, pictures: list[FactPicture]) -> None:
        """Согреть паспорта экрана по одному, начиная с наведённой плитки.

        У каждого паспорта свой поход в Wikipedia. Восемь потоков сразу выбивали
        источник в молчание; последовательность сохраняет Q-id видимого экрана и
        оставляет единственную сетевую руку открытой карточке.
        """
        wanted = list(dict.fromkeys(pictures[:PASSPORT_LIMIT]))
        with self._lock:
            self._passports = wanted
            if self._passport_running:
                return
            self._passport_running = True
        self.spawn(self._pump_passports)

    def _pump_passports(self) -> None:
        """Снять текущий экран паспортов, уступая новому экрану до следующего похода."""
        while True:
            with self._lock:
                if not self._passports:
                    self._passport_running = False
                    return
                picture = self._passports.pop(0)
            try:
                self.passport(picture)
            except Exception:
                continue


__all__ = ["WarmTarget", "WarmTargets"]
