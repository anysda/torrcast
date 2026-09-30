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
    beside: Sequence[Ask] = (),
) -> None:
    """Land every late hit as its source answers; a silent source is unknown, not a miss.

    A miss of a picture judged ``beside`` a calm claim is booked by the claim's owner alone
    (:func:`hass.hit_book.hit_book`): booked here too, one empty answer counted twice.
    """
    began = owner._now()

    def land(found: dict[Ask, list[str]]) -> None:
        with owner._lock:
            for ask in found:
                _settle(owner, _name(ask))
            # Another verdict judging the same picture beside this one may carry its bytes already.
            fresh = {ask: pages for ask, pages in found.items() if not owner._holds(_name(ask))}
            for ask in fresh:
                owner._pending[_name(ask)] = threading.Event()
        if fresh:
            threading.Thread(target=owner._fill, args=(fresh, True), daemon=True).start()

    try:
        answered: dict[Ask, list[str]] | None = finish(asks, timeout, land)
    except Exception:
        answered = None
    troubled = answered is None or owner._weather.troubled_since(began)
    with owner._lock:
        for ask in asks:
            if _name(ask) in owner._late_names:
                # Only the in-flight mark: a real miss another verdict booked meanwhile stays.
                owner._late_names.discard(_name(ask))
                if ask in beside:
                    continue
                unknown = troubled or ask not in (answered or {})
                owner._missed(_name(ask), unknown, owner._weather.calm_at())


def _settle(owner: Any, name: str) -> None:
    """Drop the in-flight mark under the owner's lock; the retry count stays for the next miss."""
    owner._late_names.discard(name)
    owner._tried.pop(name, None)


__all__ = ["late_posters"]
