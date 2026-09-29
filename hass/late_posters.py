"""Finish the visible row's poster verdicts that its quick race left in flight."""

from __future__ import annotations

import threading
from collections.abc import Callable, Sequence
from typing import Any

from hass.hit_ask import _name
from torrcast.domain.facts.ask import Ask

Land = Callable[[dict[Ask, list[str]]], None]


def late_posters(
    owner: Any,
    asks: list[Ask],
    finish: Callable[[Sequence[Ask], float, Land], dict[Ask, list[str]]],
    timeout: float,
) -> None:
    """Land every late hit as its source answers; a silent source is unknown, not a miss."""
    began = owner._now()

    def land(found: dict[Ask, list[str]]) -> None:
        with owner._lock:
            for ask in found:
                _settle(owner, _name(ask))
                owner._pending[_name(ask)] = threading.Event()
        threading.Thread(target=owner._fill, args=(found, True), daemon=True).start()

    try:
        answered: dict[Ask, list[str]] | None = finish(asks, timeout, land)
    except Exception:
        answered = None
    troubled = answered is None or owner._weather.troubled_since(began)
    with owner._lock:
        for ask in asks:
            if _name(ask) in owner._late_names:
                _settle(owner, _name(ask))
                unknown = troubled or ask not in (answered or {})
                owner._missed(_name(ask), unknown, owner._weather.calm_at())


def _settle(owner: Any, name: str) -> None:
    """Drop the in-flight mark under the owner's lock; the retry count stays for the next miss."""
    owner._late_names.discard(name)
    owner._tried.pop(name, None)


__all__ = ["late_posters"]
