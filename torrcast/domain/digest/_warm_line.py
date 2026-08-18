"""Строки выжимки про прогрев: вытеснение, кусок мимо сетки и сколько уже готово.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.digest._words import _gb, _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def _warm_line(rec: Mapping[str, JsonValue], stamp: str) -> str | None:
    """Событие прогрева одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "evict":
        who = rec.get("title") or rec.get("key", "?")
        return (
            f"{stamp}бюджет прогрева вытеснил «{who}»:"
            f" освободилось {_gb(json_number(rec.get('freed', 0.0)))}"
            f" под {_gb(json_number(rec.get('need', 0.0)))}"
        )
    if event == "skew":
        end = "место осталось непрогретым" if rec.get("hole") else "кусок переложен заново"
        return (
            f"{stamp}v{rec.get('slot', '?')} лёг мимо сетки:"
            f" начало {json_number(rec.get('off', 0.0)):+.2f} с"
            f" от границы {_hms(json_number(rec.get('want', 0.0)))} - {end}"
        )
    if event in {"ready", "stall"}:
        head = (
            f"{stamp}прогрето {_hms(json_number(rec.get('secs', 0.0)))}"
            f" из {_hms(json_number(rec.get('dur', 0.0)))}"
            f" ({json_number(rec.get('share', 0.0)) * 100:.0f} %,"
            f" {_gb(json_number(rec.get('size', 0.0)))})"
        )
        why = rec.get("why")
        return f"{head} - прогрев встал: {why}" if why else head
    return None
