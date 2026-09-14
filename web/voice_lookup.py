"""Дорожки раздачи, которую играл бы показ: фоновый отбор с кэшем в памяти.

Имена студий из названий раздач звуком не являются: английской, японской и прочей
оригинальной дорожки в них нет вовсе, и карточка их не показывала. Дорожки читает
только поток, поэтому карточка идёт тем же отбором, что и ``cast voices`` (:func:`
torrcast.usecases.voices_command._cmd_voices`), фоном и без показа, как разбор серий
(:mod:`web.episode_lookup`).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.cli.parse_args import parse_args
from torrcast.domain.info_hash import info_hash
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.progress.slot import progress
from torrcast.ports.torrent_engines import TorrentEngines
from torrcast.runtime.native_picture import native_picture
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench
from web.episode_lookup import RETRY, Spawn
from web.heard import Heard


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="voice-lookup").start()


@dataclass
class VoiceLookup:
    """Кэш «картина -> дорожки её раздачи» на процесс; строит фон, читает каждый запрос."""

    engines: TorrentEngines
    spawn: Spawn = _daemon
    clock: Callable[[], float] = time.monotonic
    _heard: dict[str, tuple[Heard | None, float]] = field(default_factory=dict)
    _pending: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def of(self, plan: Plan, query: str, base_url: str) -> tuple[Heard | None, bool]:
        """Дорожки, если уже прочитаны, и «ещё в пути»; иначе завести отбор фоном."""
        key = plan.picture.key
        with self._lock:
            cached = self._heard.get(key)
            if cached is not None and (cached[0] is not None or cached[1] > self.clock()):
                return cached[0], False
            if key not in self._pending:
                self._pending.add(key)
                start = True
            else:
                start = False
        if start:
            self.spawn(lambda: self._build(plan, query, base_url))
        with self._lock:
            cached = self._heard.get(key)
            if cached is None or key in self._pending:
                return None, True
            return cached[0], False

    def _build(self, plan: Plan, query: str, base_url: str) -> None:
        """Отобрать раздачу, прочитать её дорожки и убрать за собой всё прогретое."""
        heard: Heard | None = None
        args = parse_args([query])
        bench = Bench(self.engines(base_url), choose=file_picker(args))
        try:
            native_picture(plan.picture, query)
            prep = bench.resolve(plan, args, progress())
            release = info_hash(prep.release)
            heard = Heard(prep.found, plan.picture.native, prep.release.studios, release)
        except TorrcastError:
            heard = None
        finally:
            bench.drop_all()
            with self._lock:
                self._heard[plan.picture.key] = (heard, self.clock() + RETRY)
                self._pending.discard(plan.picture.key)


__all__ = ["VoiceLookup"]
