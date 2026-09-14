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

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.info_hash import info_hash
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.pick_settings import PICK_BUDGET
from torrcast.domain.profile import Profile
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.progress.slot import progress
from torrcast.ports.torrent_engines import TorrentEngines
from torrcast.runtime.native_picture import native_picture
from torrcast.usecases.playback.file_picker import file_picker
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select_bench.bench import Bench
from web.card_warm import CardWarm
from web.episode_lookup import RETRY, Spawn
from web.heard import Heard


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="voice-lookup").start()


def _show_profile(config: Config) -> Profile:
    """Профиль, которым судит показ: карточка, судящая иначе, выбрала бы не ту раздачу."""
    return detector.detect(config).profile


@dataclass
class VoiceLookup:
    """Кэш «картина -> дорожки её раздачи» на процесс; строит фон, читает каждый запрос."""

    engines: TorrentEngines
    spawn: Spawn = _daemon
    warms: CardWarm = field(default_factory=CardWarm)
    profile_of: Callable[[Config], Profile] = _show_profile
    clock: Callable[[], float] = time.monotonic
    _heard: dict[str, tuple[Heard | None, float]] = field(default_factory=dict)
    _pending: set[str] = field(default_factory=set)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def of(
        self, plan: Plan, query: str, config: Config, live: Entry | None = None
    ) -> tuple[Heard | None, bool]:
        """Дорожки, если уже прочитаны, и «ещё в пути»; иначе завести отбор фоном.

        Прочитанные дорожки не держат раздачу: карточка, открытая заново, греет её снова
        (:class:`web.card_warm.CardWarm`) - сразу той раздачей, что отбор уже выбрал.
        Живая закладка (``live``) главнее отбора: «Играть» продолжит её, и дорожки с
        прогревом - её раздачи и серии (:func:`_bookmark`).
        """
        key = plan.picture.key
        mark, label = _bookmark(live)
        with self._lock:
            cached = self._heard.get(key)
            known = cached is not None and (cached[0] is not None or cached[1] > self.clock())
            heard = cached[0] if cached is not None and known else None
            if heard is not None and mark and heard.release != mark:
                known, heard = False, None  # закладка появилась позже отбора карточки
            if known and (heard is None or self.warms.holds(key)):
                return heard, False
            start = key not in self._pending
            self._pending.add(key)
        if start:
            release = mark or (heard.release if heard is not None else "")
            self.spawn(lambda: self._build(plan, query, config, release, bool(mark), label))
        if known:
            return heard, False
        with self._lock:
            cached = self._heard.get(key)
            if cached is None or key in self._pending:
                return None, True
            return cached[0], False

    def _build(
        self,
        plan: Plan,
        query: str,
        config: Config,
        release: str = "",
        pinned: bool = False,
        label: str = "",
    ) -> None:
        """Отобрать раздачу, прочитать её дорожки и оставить греться только выбранную.

        ``pinned`` - раздачу назвала закладка: отбор, взявший другую, дорожек не отдаёт,
        потому что сыграет не она, а меню чужих дорожек соврало бы.
        """
        heard: Heard | None = None
        words = [query, label] if label else [query]
        args = parse_args([*words, "--card-release", release] if release else words)
        profile = self.profile_of(config)
        engines = self.engines(config.torrserver_url)
        make = lambda: Bench(engines, choose=file_picker(args), profile=profile)  # noqa: E731
        warm, fresh = self.warms.open(plan.picture.key, make)
        prep = None
        left = released = False
        try:
            if fresh:
                native_picture(plan.picture, query)
                prep = warm.bench.resolve(plan, args, self.warms.progress(warm, progress()))
            else:  # картину уже отбирает показ: дорожки - его раздачи
                warm.chosen.wait(PICK_BUDGET)
                prep = warm.prep
        except self.warms.stopped():
            left = not warm.taken
            if not left:  # показ ждёт стенд, пока его не отпустят: отпустить до ответа
                self.warms.finish(warm, None)
                released = True
                warm.chosen.wait(PICK_BUDGET)
                prep = warm.prep
        except TorrcastError:
            prep = None
        finally:
            foreign = pinned and prep is not None and info_hash(prep.release) != release
            if fresh and not released:  # чужую закладке раздачу не греют: играть её не будут
                self.warms.finish(warm, None if foreign else prep)
            if prep is not None and not foreign:
                release = info_hash(prep.release)
                heard = Heard(prep.found, plan.picture.native, prep.release.studios, release)
            with self._lock:
                if not left:  # ушедшая карточка ответа не узнала, и «дорожек нет» не пишется
                    self._heard[plan.picture.key] = (heard, self.clock() + RETRY)
                self._pending.discard(plan.picture.key)


def _bookmark(live: Entry | None) -> tuple[str, str]:
    """Раздача и серия, которые продолжит «Играть»; пусто - закладка не ответит.

    Условие то же, что у показа (:func:`torrcast.usecases.cast_command._bookmark.
    _continue_picked`): фильм - начатый и не досмотренный, сериал - любое место до конца.
    """
    if live is None or live.done or not live.magnet or not (live.serial or live.resumable):
        return "", ""
    return magnet_hash(live.magnet), live.label


__all__ = ["VoiceLookup"]
