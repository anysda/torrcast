"""Гонка двух источников постеров за один видимый ряд: оба ответа хранятся, когда придут.

Ряд берёт ответ того, кто успел первым (:class:`hass.both_posters.BothPosters`), но ответ
проигравшего не выбрасывается: запросы уже на проводе, и он доезжает в ту же память.
Отсюда поздняя посадка промолчавших картин и запасные адреса плитки, чей хост замолчал
(:mod:`hass.spare_bodies`), - оба без второго круга по сети.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable, Sequence
from typing import Any

from torrcast.domain.facts.ask import Ask


class PosterRace:
    """Both sources in flight for one visible batch; either answer is kept when it comes."""

    def __init__(self, first: Callable[..., Any], second: Callable[..., Any]) -> None:
        self.moved = threading.Event()
        self.first = _Call(first, self.moved)
        self.second = _Call(second, self.moved)

    def said(self, asks: Sequence[Ask]) -> dict[Ask, list[str]]:
        """Pages by trust order; ``[]`` only when both answered, and silence is left out."""
        first, second = self.first.so_far(), self.second.so_far()
        both = self.first.answer is not None and self.second.answer is not None
        return {
            ask: first.get(ask) or second.get(ask) or []
            for ask in asks
            if first.get(ask) or second.get(ask) or both
        }

    def spare(self, ask: Ask, deadline: float) -> list[str]:
        """Every address both sources named for ``ask``, trusted first, waiting only in memory.

        A source still on the wire is waited for until ``deadline``: its request was paid by
        the race, so the wait costs time, never a new request.
        """
        for call in (self.first, self.second):
            call.done.wait(max(0.0, deadline - time.monotonic()))
        return [*self.first.so_far().get(ask, []), *self.second.so_far().get(ask, [])]

    def over(self) -> bool:
        return self.first.done.is_set() or self.second.done.is_set()

    def land(
        self, asks: Sequence[Ask], deadline: float, land: Callable[[dict[Ask, list[str]]], None]
    ) -> dict[Ask, list[str]]:
        """Hand over each hit the moment its source answers; the rest waits for the other."""
        landed: set[Ask] = set()

        def hits() -> bool:
            now = {ask: pages for ask, pages in self.said(asks).items() if pages}
            fresh = {ask: pages for ask, pages in now.items() if ask not in landed}
            if fresh:
                landed.update(fresh)
                land(fresh)
            return self.first.done.is_set() and self.second.done.is_set()

        self.wait(deadline, hits)
        return self.said(asks)

    def wait(self, deadline: float, enough: Callable[[], bool]) -> None:
        """Wake on every finished source until ``enough`` says so or the deadline passes."""
        while not enough() and time.monotonic() < deadline:
            self.moved.wait(max(0.0, deadline - time.monotonic()))
            self.moved.clear()
            if self.first.done.is_set() and self.second.done.is_set():
                enough()
                return


class _Call:
    """One independent source call; a raised one ends with no answer at all.

    A source that hands pictures over one by one (``wanted_each``) wakes the race on each.
    """

    def __init__(self, ask: Callable[[Callable[..., None]], Any], moved: threading.Event) -> None:
        self.done = threading.Event()
        self.answer: dict[Ask, list[str]] | None = None
        self.heard: dict[Ask, list[str]] = {}

        def heard(part: dict[Ask, list[str]]) -> None:
            self.heard.update(part)
            moved.set()

        def run() -> None:
            try:
                self.answer = ask(heard)
            except Exception:
                pass
            finally:
                self.done.set()
                moved.set()

        threading.Thread(target=run, daemon=True, name="poster-source").start()

    def so_far(self) -> dict[Ask, list[str]]:
        """The whole answer once in, else the pictures handed over so far."""
        return self.answer if self.answer is not None else dict(self.heard)
