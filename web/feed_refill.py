"""Добор ленты холодной полки к сроку: переспрос только недосчитанных индексеров.

Лента врозь (:func:`torrcast.adapters.prowlarr.feed_apart.feed_apart`) отдаёт то, что
успели принести, и считает недосчитанных. Прежде их строки приносил следующий заход
ленты по всем индексерам после паузы в 10 с: полка, честно ждавшая его, гасила счётчик
на 52-77 с от старта (серия r10, TC-1322). Здесь недосчитанные переспрашиваются сразу и
отдельно, в своём потоке, пока не наступит срок обложек захода (:mod:`web.fill_deadline`):
что пришло к сроку, встаёт на полку с обложками того же срока, остальное ждёт пересборки.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from typing import Final

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.feed_row import FeedRow
from torrcast.domain.feed_rows import Again

#: Отказ пришёл быстрее этого - переспрос ждёт остаток паузы, а не долбит Prowlarr.
PAUSE: Final = 1.0


@dataclass
class FeedRefill:
    """Строки, добранные к ``until`` (``time.monotonic``); ``short`` - недосчёт остался."""

    again: Again | None
    until: float
    short: bool = False
    _rows: list[FeedRow] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _thread: threading.Thread | None = None

    def start(self) -> FeedRefill:
        """Пустить переспрос; нечего добирать - ничего не встаёт."""
        self.short = self.again is not None
        if self.again is not None:
            self._thread = threading.Thread(target=self._run, name="feed-refill", daemon=True)
            self._thread.start()
        return self

    def _run(self) -> None:
        again = self.again
        within = f"{self.until - time.monotonic():.1f}"
        print(phrase("systemd.shelf.feed_short", within=within), flush=True)
        while again is not None and (left := self.until - time.monotonic()) > 0:
            began = time.monotonic()
            got = again(left)
            with self._lock:
                self._rows.extend(got)
                self.short = got.missed > 0
            again = got.again
            if got or again is None:  # the journal tells when the missed indexer came in
                count, missed = len(got), got.missed
                print(phrase("systemd.shelf.feed_refilled", count=count, missed=missed), flush=True)
            now = time.monotonic()
            if not got and again is not None:  # a quick refusal: wait out the pause
                time.sleep(max(min(PAUSE - (now - began), self.until - now), 0.0))

    def take(self) -> list[FeedRow]:
        """Строки, пришедшие с прошлого вопроса."""
        with self._lock:
            rows, self._rows = self._rows, []
        return rows

    def pending(self) -> bool:
        """Добранное ещё не взято или переспрос идёт и успевает к сроку."""
        with self._lock:
            waiting = bool(self._rows)
        alive = self._thread is not None and self._thread.is_alive()
        return waiting or (alive and time.monotonic() < self.until)


__all__ = ["PAUSE", "FeedRefill"]
