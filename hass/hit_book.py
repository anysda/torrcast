"""Запись приговора о картинах находок в память моста (:class:`hass.hit_claims.HitClaims`).

Судей у картины бывает двое: спокойный путь, держащий заявку, и видимый ряд, судящий её рядом
(:data:`hass.hit_claims._BESIDE`). Байты везёт первый, кто назвал адрес; промах картины рядом
пишет только хозяин заявки - иначе пустая гонка ряда отложила бы картину, у которой обложку
ещё несёт спокойный путь.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from hass.hit_ask import _name
from torrcast.domain.facts.ask import Ask


def hit_book(
    claims: Any,
    asked: Sequence[Ask],
    said: dict[Ask, list[str]] | None,
    later: Sequence[Ask],
    beside: Sequence[Ask],
    troubled: bool,
    calm_at: float,
) -> dict[Ask, list[str]]:
    """Записать приговор; вернуть адреса тех, чьи байты ещё никто не везёт."""
    found: dict[Ask, list[str]] = {}
    with claims._lock:
        claims._late_names.update(_name(ask) for ask in later)
        for ask in (ask for ask in asked if ask not in later):
            name, pages = _name(ask), (said or {}).get(ask)
            if claims._holds(name):
                continue
            if pages:
                claims._pending[name] = threading.Event()
                found[ask] = pages
            elif ask not in beside:
                claims._missed(name, troubled or ask not in (said or {}), calm_at)
    return found


__all__ = ["hit_book"]
