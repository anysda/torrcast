"""Раздачи картины, пока её круг ещё идёт: то, что индексеры уже прислали.

Карточка плитки открывается раньше круга раздач (:mod:`web.preview`), и до его конца
счёт раздач стоял нулём, а потом приезжал одним куском: круг ждёт опорных, добор второй
строкой и разбор серий. Индексеры же отвечают порознь, и ответ первого уже называет
раздачи картины. Здесь их считают тем же разбором, что и круг
(:func:`~torrcast.usecases.discover.recognized_pick.recognized_pick`), по выдаче, которую
идущий круг уже держит (:data:`~torrcast.usecases.discover.circle_watch.WATCH`), ни одного
запроса в сеть не добавляя. Итог круга эти числа не решают: он приходит полным телом.

Считается только то, что круг уже взял в итог (:meth:`~torrcast.adapters.prowlarr.
indexer_circle.IndexerCircle.inflight`): отрезанный опоздавший и выдача доборов входят в
число вместе с итогом. Так счёт до итога его не больше и на экране только растёт.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from torrcast.usecases.discover.circle_watch import WATCH, Rows
from torrcast.usecases.discover.recognized_pick import recognized_pick
from web.card_lookup import _score

if TYPE_CHECKING:
    from torrcast.domain.picture import Picture

_lock = threading.Lock()
#: Последняя находка по строке и ключу: число строк, из которых её собрали, и когда.
#: Долгий заход оглядывается двадцать раз в секунду, а разбор нужен только на новых строках.
_seen: dict[tuple[str, str], tuple[int, Picture | None, float]] = {}
#: Сколько находка держит счёт после того, как круг её больше не показывает: между концом
#: круга и его записью в кэш строк нет вовсе, а новый заход круга начинает выдачу с нуля.
HOLD: Final = 60.0
_clock: Callable[[], float] = time.monotonic


def early_picture(query: str, key: str, rows: Callable[[str], Rows] = WATCH.rows) -> Picture | None:
    """Картина ключа по выдаче идущего круга; ничего не пришло или её там нет - ``None``.

    Счёт не идёт назад, пока карточка ждёт: на экране он только растёт (замер: 6 раздач,
    потом 0 в щель между концом круга и его записью, потом снова 6).
    """
    raw, named, known = rows(query)
    size = len(raw) + len(named)
    now = _clock()
    with _lock:
        seen = _seen.get((query, key))
    if seen is not None and now - seen[2] > HOLD:
        seen = None
    if seen is not None and seen[0] == size:
        return seen[1]
    picture = _pick(query, key, rows=(raw, named, known)) if size else None
    if seen is not None and _count(seen[1]) > _count(picture):
        return seen[1]
    with _lock:
        if len(_seen) > 64:  # a screenful of cards, not a history
            _seen.clear()
        _seen[(query, key)] = size, picture, now
    return picture


def _pick(query: str, key: str, rows: Rows) -> Picture | None:
    """Разобрать выдачу тем же правилом, что круг, и найти в ней картину ключа."""
    pictures, found = recognized_pick(query, *rows)
    # Тем же правилом, что карточка ищет свою картину в круге (:func:`web.card_lookup.card_lookup`).
    best = max([*found, *pictures], key=lambda each: _score(each, key), default=None)
    return best if best is not None and _score(best, key) else None


def _count(picture: Picture | None) -> int:
    return len(picture.releases) if picture is not None else 0


__all__ = ["early_picture"]
