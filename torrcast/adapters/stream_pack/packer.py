"""Один прогон упаковки: процесс ffmpeg и всё, что о нём спрашивает показ.

Заводит его лента (:mod:`torrcast.usecases.feed_pack.feed`), а зовёт ещё и перекод.
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import IO, Any

from torrcast.adapters.stream_pack.packer_finished import _cuts, _drift, _finished
from torrcast.adapters.stream_pack.packer_measure import _eta, _frontier, _pending
from torrcast.adapters.stream_pack.packer_publish import _lay_out
from torrcast.adapters.stream_pack.packer_state import _Asked, _State, _Told
from torrcast.adapters.stream_pack.packer_stop import _stop, _why
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.feed_grid import FeedGrid


@dataclass(slots=True)
class Packer(_State):
    """Один прогон упаковки: процесс ffmpeg, который пакует фильм с сегмента ``first``.

    ffmpeg пишет в свой каталог (:data:`PACK_DIR`), наружу сегменты выкладывает
    :meth:`publish` переименованием. Так решаются сразу две вещи: наружу не попадает
    недописанный кусок и не затирается чужой (см. :data:`PACK_DIR`).
    """

    @classmethod
    def start(
        cls,
        command: list[str],
        out: Path,
        run: Path,
        first: int = 0,
        spare: Path | None = None,
        told: _Told | None = None,
        hold: _Asked | None = None,
        shrink: _Asked | None = None,
        last: int = -1,
        at: float = 0.0,
        rate: float = 0.0,
        burst: float = 0.0,
        grid: FeedGrid | None = None,
        cap: int = CAUTIOUS.max_segment_bytes,
        container: SegmentContainer = MPEGTS,
        *,
        spawn: Callable[..., Any] = subprocess.Popen,
        log_file: Callable[[], IO[bytes]] = tempfile.TemporaryFile,
        now: Callable[[], float] = time.monotonic,
    ) -> Packer:
        """Поднять ffmpeg и вернуть идущий прогон.

        ``spawn``, ``log_file`` и ``now`` - чем поднимается процесс, куда пишется его брань
        и по каким часам меряется прогон.
        Доводами, а не именами внутри модуля: прежде стенд подменял :mod:`subprocess` и
        :mod:`tempfile` целиком, вместе с их же классами ошибок, - то есть знал не
        договор завода, а порядок имён под его крышкой.
        """
        log = log_file()
        shutil.rmtree(run, ignore_errors=True)
        run.mkdir(parents=True, exist_ok=True)
        began = now()
        try:
            proc = spawn(command, stdout=subprocess.DEVNULL, stderr=log)
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        return cls(
            proc=proc,
            out=out,
            run=run,
            first=first,
            log=log,
            spare=spare,
            told=told,
            hold=hold,
            shrink=shrink,
            last=last,
            began=began,
            now=now,
            at=at,
            rate=rate,
            burst=burst,
            grid=grid,
            cap=cap,
            container=container,
        )

    def eta(self, film: float) -> float:
        """Через сколько секунд ffmpeg дочитает вход до секунды ``film`` (:func:`_eta`)."""
        return _eta(self, film)

    def finished(self) -> bool:
        """Прогон дочитал вход до конца, а не просто вышел (:func:`_finished`)."""
        return _finished(self)

    def publish(self) -> None:
        """Выложить готовое одним заходом, не удерживая конкурирующий горячий путь."""
        if not self.publish_lock.acquire(blocking=False):
            return
        try:
            self._publish()
        finally:
            self.publish_lock.release()

    def _publish(self) -> None:
        """Выложить наружу дописанные куски (:func:`_lay_out`)."""
        _lay_out(self, self.finished)

    def cuts(self) -> list[tuple[int, float, float]]:
        """Что ffmpeg нарезал на самом деле, по его же списку (:func:`_cuts`)."""
        return _cuts(self)

    def drift(self, grid: FeedGrid) -> float:
        """Насколько нарезанное разошлось с манифестом, секунды (:func:`_drift`)."""
        return _drift(self, grid)

    def pending(self) -> int:
        """Сколько байт прогон написал в tmpfs, но наружу не отдал (:func:`_pending`)."""
        return _pending(self)

    def frontier(self) -> int:
        """Последний готовый сегмент в каталоге показа; ``first - 1`` — готового нет.

        ⚠️ Это **не** край прогона (:attr:`edge`): счёт идёт глобом каталога, где лежат и
        куски прошлых прогонов, поэтому после перемотки назад число врёт вверх. Решения
        об упаковке на нём больше не строятся (:meth:`Feed._steer`); осталось оно ровно
        под :meth:`Feed.front` — запас показа для сторожа приёмника, который доказан на
        живом ТВ, и менять его без такой же живой проверки нельзя.
        """
        self.publish()
        return _frontier(self)

    def halt(self, reason: str = "пауза на пульте") -> None:
        """Погасить упаковку, **не трогая уже упакованное**: приёмник на паузе, и копить
        сегменты в tmpfs незачем. Возобновление — новый прогон (:meth:`Feed.segment`).

        Раньше на этом месте стояла пауза сигналом (SIGSTOP). Она и оказалась причиной
        подвиса: манифест замирает, а приёмник намертво виснет в BUFFERING —
        держит коннект и не запрашивает ничего. Поэтому процесс именно завершается.
        """
        self.halted = True
        self.stop(keep_files=True, reason=reason)

    def poll(self) -> int | None:
        return self.proc.poll()

    def why(self) -> str:
        """Почему прогон кончился — наружу без трейсбеков (:func:`_why`)."""
        return _why(self)

    def stop(self, keep_files: bool = False, reason: str = "") -> None:
        """Снять прогон, оставив показу уже выложенное (:func:`_stop`)."""
        _stop(self, self.publish, keep_files, reason)
