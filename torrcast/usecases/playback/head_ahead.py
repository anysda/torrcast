"""Тяжёлая голова показа ложится на полку прогрева раньше юнита: с отбора и с клика.

Показ берёт кусок с полки раньше, чем ждёт свой кодировщик
(:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`), поэтому перекод головы, начатый
до юнита, - это секунды первого кадра: юнит поднимается 0.6 с, и только потом его
кодировщик берётся за голову, которая на 4 ядрах кодируется ещё 3-3.6 с («Призрак в
доспехах», 1080p 11.2 Мбит/с). Голова одна на процесс: новая снимает прежнюю.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import torrcast.usecases.playback._show_state as _state
from torrcast.domain.magnet_hash import magnet_hash
from torrcast.domain.segment_container import MPEGTS
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback.hls_root import hls_root
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.playback.voice_source import voice_source
from torrcast.usecases.warm.lay_head import lay_head
from torrcast.usecases.warm.vault import Vault
from torrcast.usecases.warm.warm_key import warm_key
from torrcast.usecases.warm.warm_root import warm_root

if TYPE_CHECKING:
    from torrcast.domain.config import Config
    from torrcast.domain.entry import Entry
    from torrcast.domain.profile import Profile
    from torrcast.ports.recode.encoding_rate import EncodingRate
    from torrcast.ports.torrent_engine import TorrentEngine
    from torrcast.usecases.playback.media_grid import MediaGrid


@dataclass
class _Job:
    """Одна голова: чья полка и чем её снять."""

    key: str
    owner: str
    halt: threading.Event = field(default_factory=threading.Event)


def _daemon(job: Callable[[], None]) -> None:
    """Боевой запуск фона: поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="head-ahead").start()


@dataclass
class HeadAhead:
    """Единственная голова, которая греется в процессе заранее."""

    spawn: Callable[[Callable[[], None]], None] = _daemon
    lay: Callable[..., bool] = lay_head
    _job: _Job | None = None
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def want(
        self, config: Config, profile: Profile, engine: TorrentEngine, entry: Entry, owner: str = ""
    ) -> None:
        """Греть голову записи ``entry`` фоном; прежняя другая голова снимается.

        ``owner`` - картина карточки, чей уход голову снимает; пусто - голова показа, её
        не снимает никто. Та же голова, спрошенная показом, переходит к нему.
        """
        self.spawn(lambda: self._run(config, profile, engine, entry, owner))

    def drop(self, owner: str) -> None:
        """Снять голову карточки ``owner``: карточка ушла, играть её не будут."""
        with self._lock:
            job = self._job
            if job is None or not owner or job.owner != owner:
                return
            self._job = None
        job.halt.set()

    def _run(
        self, config: Config, profile: Profile, engine: TorrentEngine, entry: Entry, owner: str
    ) -> None:
        try:
            head = _plan(config, profile, engine, entry)
        except TorrcastError as exc:  # заранее: не вышло - показ возьмёт голову сам
            journal().mark("голова заранее не собралась", почему=type(exc).__name__)
            return
        with self._lock:
            old = self._job
            if head is None:
                return
            if old is not None and old.key == head.vault.key:
                old.owner = old.owner and owner  # показ забрал голову карточки
                return
            self._job = job = _Job(head.vault.key, owner)
        if old is not None:
            old.halt.set()
        self.lay(
            head.vault, head.source, entry.audio, head.voice, head.grid, head.slot, head.encode,
            profile.max_segment_bytes, MPEGTS, job.halt,
        )  # fmt: skip
        with self._lock:
            if self._job is job:
                self._job = None


@dataclass(frozen=True)
class _Head:
    """Что и куда кладётся: полка показа, его источник и сетка, место и цель перекода."""

    vault: Vault
    source: str
    voice: str
    grid: MediaGrid
    slot: int
    encode: EncodingRate


def _plan(config: Config, profile: Profile, engine: TorrentEngine, entry: Entry) -> _Head | None:
    """Полка и перекод головы теми же числами, что у показа (:func:`_play`, :func:`_tract`).

    ``None`` - греть нечего: прогрев выключен, файл идёт перекодом целиком, голова лёгкая
    или приёмник берёт куски fMP4 (у них своя голова ``init.mp4``).
    """
    if not config.warm or not config.recode or profile.segment_container != MPEGTS:
        return None
    torrent = magnet_hash(entry.magnet)
    source = engine.stream_url(torrent, entry.file_idx)
    size = next((item.size for item in engine.files(torrent) if item.index == entry.file_idx), 0)
    voice = voice_source(engine, torrent, entry)
    mbit = max(0.0, entry.vbps)
    grid, whole = layout(
        config, source, entry.dur, entry.codec, mbit, depth=entry.depth,
        profile=profile, frame=entry.frame, hdr=entry.hdr, file_size=size,
    )  # fmt: skip
    if whole is not None:
        return None
    recoder = _recoder(
        source,
        entry.audio,
        grid,
        hls_root(config.hls_dir) / _state.RECODE_DIR,
        config,
        video_mbit=mbit,
        profile=profile,
        video_mbit_estimated=entry.vbps_estimated,
        voice=voice,
    )
    slot = grid.slot_at(entry.pos)
    spots = () if recoder is None else tuple(recoder.targets)
    if recoder is None or slot not in spots:
        return None
    vault = Vault(
        root=warm_root(config.warm_dir),
        key=warm_key(source, entry.audio, grid, None, spots, MPEGTS, voice, recoder.encode),
        budget=int(config.warm_budget_gb * 1e9),
        title=" ".join(filter(None, (entry.title, entry.label))),
        container=MPEGTS,
    )
    fastest = recoder.pace.table()[-1][0]
    journal().mark("голова заранее", слот=slot, ключ=vault.key)
    return _Head(vault, source, voice, grid, slot, recoder.fit(grid.span(slot), fastest))


#: Голова процесса: её греют карточка и клик, а берёт показ с полки.
HEAD = HeadAhead()

__all__ = ["HEAD", "HeadAhead"]
