"""Серии сериала по TVmaze: сезоны, номера и даты выхода по IMDb-id, с кэшем на диске.

TVmaze нумерует сериал эфирными сезонами, как его раскладывают раздачи («Интерны» -
четырнадцать сезонов по 20, у IMDb - четыре по 60), и знает даты ещё не вышедших серий.
Ответ живёт на диске сутки: карточка берёт его без сети, устаревший отдаётся сразу и
обновляется фоном. Холодный вопрос ждёт сеть не дольше, чем просит карточка; молчание
сети запоминается на :data:`RETRY` и карточку не держит.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from torrcast.adapters.filesystem.state.state_path import state_path
from torrcast.domain.facts.settings import USER_AGENT

#: Серии: (сезон, номер) -> (момент выхода для сравнения, дата выхода для глаз).
Aired = dict[tuple[int, int], tuple[str, str]]
#: Кто спрашивает адрес: разобранный JSON или ``None`` на 404 («не знаю такого»).
Fetch = Callable[[str], object]
#: Кто разносит фоновый вопрос по потоку; в бою - поток-демон.
Spawn = Callable[[Callable[[], None]], None]
_BASE = "https://api.tvmaze.com"
#: Потолок одного HTTP-вопроса: дольше этого сеть считается молчащей.
TIMEOUT = 5.0
#: Сколько ответ годен без обновления.
FRESH = 24 * 3600.0
#: Неудачу переспрашивать не раньше этого.
RETRY = 60.0
_TCONST = re.compile(r"tt\d{1,10}")


def _get(url: str) -> object:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urlopen(request, timeout=TIMEOUT) as response:
            return json.load(response)
    except HTTPError as failed:
        if failed.code == 404:
            return None
        raise


def _daemon(job: Callable[[], None]) -> None:
    threading.Thread(target=job, daemon=True, name="tvmaze-episodes").start()


def _beside_state() -> Path:
    return state_path().with_name("tvmaze")


@dataclass
class TvmazeEpisodes:
    """Серии по IMDb-id на процесс: память, диск и фоновый вопрос к TVmaze."""

    where: Callable[[], Path] = _beside_state
    fetch: Fetch = _get
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.time
    _memory: dict[str, tuple[Aired, float]] = field(default_factory=dict)
    _failed: dict[str, float] = field(default_factory=dict)
    _pending: dict[str, threading.Event] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def aired(self, tconst: str, wait: float = 0.0) -> tuple[Aired, bool]:
        """Серии сериала и «ответ ещё в пути»; неизвестный сериал и молчащая сеть - пусто."""
        if not _TCONST.fullmatch(tconst):
            return {}, False
        now = self.clock()
        with self._lock:
            known = self._memory.get(tconst) or self._read(tconst)
            if known is not None:
                self._memory[tconst] = known
                if now - known[1] < FRESH:
                    return known[0], False
            event = self._pending.get(tconst)
            started = event is None and self._failed.get(tconst, 0.0) <= now
            if started:
                event = self._pending[tconst] = threading.Event()
        if started and event is not None:
            self.spawn(lambda: self._refresh(tconst, event))
        if known is not None:
            return known[0], False
        if started and event is not None and wait > 0:
            event.wait(wait)
        with self._lock:
            fresh = self._memory.get(tconst)
            return (fresh[0], False) if fresh else ({}, tconst in self._pending)

    def _refresh(self, tconst: str, event: threading.Event) -> None:
        found: Aired | None = None
        try:
            found = self._download(tconst)
            self._write(tconst, found)
        except (OSError, ValueError, TypeError):
            pass  # a stale or empty answer stays; RETRY asks again
        finally:
            with self._lock:
                if found is None:
                    self._failed[tconst] = self.clock() + RETRY
                else:
                    self._memory[tconst] = (found, self.clock())
                del self._pending[tconst]
            event.set()

    def _download(self, tconst: str) -> Aired:
        show = self.fetch(f"{_BASE}/lookup/shows?imdb={tconst}")
        if not isinstance(show, dict) or not isinstance(show.get("id"), int):
            return {}
        episodes = self.fetch(f"{_BASE}/shows/{show['id']}/episodes")
        if not isinstance(episodes, list):
            raise ValueError("episodes")
        return _episodes(episodes)

    def _read(self, tconst: str) -> tuple[Aired, float] | None:
        try:
            saved = json.loads((self.where() / f"{tconst}.json").read_text(encoding="utf-8"))
            rows = {(s, n): (when, date) for s, n, when, date in saved["episodes"]}
            return rows, float(saved["fetched"])
        except (OSError, ValueError, TypeError, KeyError):
            return None

    def _write(self, tconst: str, aired: Aired) -> None:
        folder = self.where()
        folder.mkdir(parents=True, exist_ok=True)
        rows = [[s, n, when, date] for (s, n), (when, date) in sorted(aired.items())]
        part = folder / f"{tconst}.json.part"
        part.write_text(json.dumps({"fetched": self.clock(), "episodes": rows}), encoding="utf-8")
        os.replace(part, folder / f"{tconst}.json")


def _episodes(episodes: list[object]) -> Aired:
    """Серии с номером сезона и серии; спецвыпуски без номера TVmaze не нумерует."""
    out: Aired = {}
    for episode in episodes:
        if not isinstance(episode, dict):
            continue
        season, number = episode.get("season"), episode.get("number")
        if type(season) is int and type(number) is int and season > 0 and number > 0:
            date = str(episode.get("airdate") or "")
            out[(season, number)] = (str(episode.get("airstamp") or date), date)
    return out


__all__ = ["TvmazeEpisodes"]
