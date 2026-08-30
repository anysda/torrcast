"""Строки выжимки про прогрев: вытеснение, кусок мимо сетки и сколько уже готово.

Ветка отдаёт ``None``, если событие не её: разбор идёт дальше по разборщикам
(:func:`torrcast.domain.digest._event_line._event_line`).
"""

from __future__ import annotations

from collections.abc import Mapping

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.digest._words import _gb, _hms
from torrcast.domain.json_number import json_number
from torrcast.domain.json_value import JsonValue


def _warm_line(rec: Mapping[str, JsonValue], stamp: str) -> str | None:
    """Событие прогрева одной строкой; не его событие - ``None``."""
    event = str(rec.get("event", ""))
    if event == "disabled":
        return phrase("digest.warm_off", stamp=stamp)
    if event == "evict":
        who = rec.get("title") or rec.get("key", "?")
        return phrase(
            "digest.evict",
            stamp=stamp,
            who=who,
            freed=_gb(json_number(rec.get("freed", 0.0))),
            need=_gb(json_number(rec.get("need", 0.0))),
        )
    if event == "skew":
        end = phrase("digest.skew_hole" if rec.get("hole") else "digest.skew_redone")
        return phrase(
            "digest.skew",
            stamp=stamp,
            slot=rec.get("slot", "?"),
            off=f"{json_number(rec.get('off', 0.0)):+.2f}",
            want=_hms(json_number(rec.get("want", 0.0))),
            end=end,
        )
    if event in {"ready", "stall"}:
        head = phrase(
            "digest.warmed",
            stamp=stamp,
            secs=_hms(json_number(rec.get("secs", 0.0))),
            dur=_hms(json_number(rec.get("dur", 0.0))),
            share=f"{json_number(rec.get('share', 0.0)) * 100:.0f}",
            size=_gb(json_number(rec.get("size", 0.0))),
        )
        why = rec.get("why")
        return phrase("digest.warm_stalled", head=head, why=why) if why else head
    return None
