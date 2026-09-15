"""Приговор обложек шагу поиска HA - не дольше срока: список не ждёт картинок (TC-1284).

Шаг HA ждал приговор на месте, а приговор ждёт тишину Wikimedia после 429 и чужую заявку
фоновой справки на те же картины до 9 с. На стенде это было 0.3-2.7 с поверх круга. К сроку
список уходит с именами тех картинок, чьи байты уже здесь (полка читается в самом начале
приговора), а приговор досчитывается фоном: следующий поиск получит его имена.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final

from hass.hit_ask import _about, _name
from hass.hit_posters import FIELD, hits
from torrcast.domain.json_value import JsonValue

#: Сколько шаг HA ждёт приговор обложек, секунды: спокойный приговор пачки укладывается.
VERDICT_BY: Final = 1.0


def offer_within(
    offer: Callable[[list[JsonValue]], list[JsonValue]],
    records: list[JsonValue],
    limit: float = VERDICT_BY,
) -> list[JsonValue]:
    """Записи с приговором, если он успел к ``limit``; нет - с именами легших картинок."""
    said: list[list[JsonValue]] = []
    done = threading.Event()

    def judge() -> None:
        try:
            said.append(offer(records))
        finally:
            done.set()

    threading.Thread(target=judge, daemon=True, name="ha-verdict").start()
    if done.wait(limit) and said:
        return said[0]
    return [_landed(record) for record in records]


def _landed(record: JsonValue) -> JsonValue:
    ask = _about(record)
    if isinstance(record, dict) and ask is not None and hits.has(_name(ask)):
        return {**record, FIELD: _name(ask)}
    return record


__all__ = ["VERDICT_BY", "offer_within"]
