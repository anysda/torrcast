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
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.usecases.facts import FactPicture
    from torrcast.usecases.select.plan import Plan

#: Плитка полки: запрос круга, ключ картины, название, год, вид.
WarmTarget = tuple[str, str, str, int | None, str]
Circle = Callable[[str], "list[Plan]"]
Pictures = Callable[["list[FactPicture]"], None]
Kin = Callable[["FactPicture"], None]
Ask = Callable[[Sequence[str]], int]


def _no_ask(_screen: Sequence[str]) -> int:
    """Без проводки заказ плиток кругов не ставит."""
    return 0


@dataclass
class WarmTargets:
    """Обёртка круга и заказ плиток полки; боевых собирает :mod:`web.warm_wiring`."""

    circle: Circle
    prime: Pictures
    kin: Kin
    ask: Ask = _no_ask
    _keys: dict[str, str] = field(default_factory=dict, repr=False)
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
        """Наполнить сведения плиток, потом поставить их круги в очередь."""
        self.prime([(title, year, kind) for _query, _key, title, year, kind in targets])
        with self._lock:
            self._keys.update({query.strip(): key for query, key, *_rest in targets})
        return self.ask([query for query, *_rest in targets])


__all__ = ["WarmTarget", "WarmTargets"]
