"""Показанная полка без плиток, которые заход честно назвал «не играет».

Сторож публикации (:func:`web.held_by.held_by`) держит прежнее тело, когда новый
заход подозрителен. Но честный отсев по паспорту дорожек от этого не становится ложью: без
снятия плитка, которую журнал уже назвал «не играет», стояла бы на полке до первого
захода, который сторож пропустит, а на живом стенде это не случалось часами - доля
отсева считается по немногим вынесенным приговорам и легко выходит за потолок.

Здесь с ПРЕЖНЕГО тела снимаются только приговорённые ``False`` (:class:`web.drop_count.
DropCount`); «не знаю» ничего не снимает, новых плиток не ставит. Снятие держит ту же планку
усыхания (:data:`web.held_by.SHRINK_FLOOR`): сломанный прогон, назвавший «не
играет» половину полки, не снимет её разом.
"""

from __future__ import annotations

from datetime import datetime

from torrcast.domain.json_value import JsonValue
from web.carried import CARRIED, carried
from web.drop_count import DropCount
from web.dropped_marks import DROPPED, dropped_marks
from web.held_by import SHRINK_FLOOR


def shown_pruned(
    current: dict[str, JsonValue], shelf: str, drops: DropCount, now: datetime
) -> dict[str, JsonValue] | None:
    """Прежнее тело без честно отсеянных плиток ``shelf``; ``None`` - снимать нечего или много."""
    shown = current.get(shelf)
    if not isinstance(shown, list) or not drops.dropped_keys:
        return None
    kept = [tile for tile in shown if _key(tile) not in drops.dropped_keys]
    if len(kept) == len(shown):
        return None
    tail = carried(current, shelf)
    own = len(shown) - tail
    still = sum(1 for tile in shown[own:] if _key(tile) not in drops.dropped_keys)
    if len(kept) - still < own * SHRINK_FLOOR:
        return None
    marks = current.get(CARRIED)
    return {
        **current,
        shelf: kept,
        CARRIED: {**(marks if isinstance(marks, dict) else {}), shelf: still},
        DROPPED: dropped_marks(current, shelf, drops),
        "built_at": now.isoformat(),
    }


def _key(tile: JsonValue) -> str | None:
    if not isinstance(tile, dict):
        return None
    key = tile.get("key")
    return key if isinstance(key, str) else None


__all__ = ["shown_pruned"]
