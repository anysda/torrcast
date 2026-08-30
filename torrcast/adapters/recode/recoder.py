"""Фоновый кодировщик тяжёлых кусков: работает впрок, пока играет остальное.

Поднимает его показ; спрашивают его выкладка сегментов и щупы замера."""

from __future__ import annotations

import contextlib
import signal
import threading
import time
from dataclasses import dataclass
from typing import Any

from torrcast.adapters.recode.heavy_line import _heavy_line
from torrcast.adapters.recode.hold_bulky import _hold_bulky
from torrcast.adapters.recode.hold_head import _head_pending, _hold_head
from torrcast.adapters.recode.holding import _holding
from torrcast.adapters.recode.note import _note
from torrcast.adapters.recode.pick import _pick
from torrcast.adapters.recode.recoder_state import _State
from torrcast.adapters.recode.run import _run
from torrcast.adapters.recode.work import _work
from torrcast.adapters.recode.yield_to_shrink import (
    _shrink_running,
    _shrink_touched,
    _yield_to_shrink,
)
from torrcast.domain.catalogs.phrase import phrase


@dataclass(slots=True)
class Recoder(_State):
    """Фоновый кодировщик тяжёлых кусков: работает впрок, пока играет остальное.

    Порядок работы — от места показа вперёд: ближайший тяжёлый кусок важнее дальнего, а
    перемотка меняет место показа и тем самым переприоритезирует очередь на следующем же
    заходе. Готовый кусок ложится в :data:`RECODE_DIR` и ждёт там своего часа; наружу его
    выкладывает упаковщик, когда дойдёт до этого места (:meth:`Packer.publish`).
    """

    def start(self) -> None:
        """Поднять поток кодировщика. Тяжёлых кусков нет — не поднимать вовсе."""
        if not self.targets:
            self._say(phrase("recode.no_heavy_pieces"))
            return
        self._say(_heavy_line(self))
        self.spare.mkdir(parents=True, exist_ok=True)
        self.began = time.monotonic()
        self.thread = threading.Thread(target=self._work, daemon=True, name="torrcast-recode")
        self.thread.start()

    def stop(self) -> None:
        """Снять кодировщик и его процесс. Готовые куски не трогаем — их уберёт показ.

        ⚠️ Сначала снять паузу, и только потом гасить. Заход мог замереть, уступая ужатию
        (:meth:`_yield_to_shrink`), а замерший процесс SIGTERM не обрабатывает вовсе:
        :meth:`torrcast.adapters.stream_pack.packer.Packer.stop` честно ждёт его пять секунд
        и добивает
        SIGKILL - пять секунд на конце показа за счёт человека. Оживить стоит один сигнал.
        """
        self.stopped = True
        with self.lock:
            packer, self.packer = self.packer, None
        if packer is not None:
            with contextlib.suppress(OSError, ProcessLookupError, AttributeError):
                packer.proc.send_signal(signal.SIGCONT)
            packer.stop(keep_files=True, reason=phrase("recode.show_over"))

    def opening(self, slot: int) -> None:
        """Упаковка начинается заново с сегмента ``slot``
        (:meth:`torrcast.usecases.feed_pack.feed.Feed.restart`).

        Зовётся на старте показа, на возврате с паузы и на каждой перемотке. Делает три
        вещи, и все три нужны ровно ради первого сегмента:

        * помечает ``slot`` головой прогона — только его копию можно придержать, пока
          картинки ещё нет (:meth:`holding`);
        * отматывает :attr:`edge` назад: наружу этот прогон не выложил ещё ничего, а
          старое значение осталось от прошлого места показа и заставило бы :meth:`_pick`
          пропустить саму голову (после перемотки назад — весь остаток фильма);
        * ставит :attr:`played` на начало этого сегмента. Место показа приходит в
          кодировщик раз в две секунды (:func:`torrcast.usecases.revive_playback._hold._hold`), и на
          перемотке оно столько же врёт — а очередь кодировщика решается прямо сейчас.
        """
        self.head = slot
        self.head_at = time.monotonic()
        self.edge = slot - 1
        self.played = self.grid.start(slot)

    def holding(self, slot: int, size: int = 0) -> bool:
        """Придержать ли копию куска ради перекода (:func:`_holding`)."""
        return _holding(self, slot, size)

    def note(self, slot: int, how: str) -> None:
        """Сегмент ушёл наружу: уточнить профиль и посчитать опоздания (:func:`_note`)."""
        _note(self, slot, how)

    def report(self) -> str:
        """Одна строка итога: сколько успели, сколько тяжёлых ушло как есть."""
        if not self.targets:
            return ""
        return phrase(
            "recode.report", made=self.made, seconds=f"{self.seconds:.0f}", late=self.late
        )

    # ------------------------------------------------------------------ внутреннее

    def _head_pending(self) -> bool:
        """Голову прогона ещё ждут (:func:`_head_pending`)."""
        return _head_pending(self)

    def _hold_head(self, now: float) -> bool:
        """Ждать ли перекод головы прогона (:func:`_hold_head`)."""
        return _hold_head(self, now)

    def _hold_bulky(self, slot: int, now: float) -> bool:
        """Ждать перекод слишком увесистой копии (:func:`_hold_bulky`)."""
        return _hold_bulky(self, slot, now)

    def _shrink_touched(self) -> float:
        """Когда в каталоге ужатия последний раз писали (:func:`_shrink_touched`)."""
        return _shrink_touched(self)

    def _shrink_running(self) -> bool:
        """Ужимает ли выкладка кусок прямо сейчас (:func:`_shrink_running`)."""
        return _shrink_running(self)

    def _yield_to_shrink(self, packer: Any) -> float:
        """Замереть, пока идёт ужатие на месте (:func:`_yield_to_shrink`)."""
        return _yield_to_shrink(self, packer)

    def _pick(self) -> tuple[int, int] | None:
        """Ближайший заход кодировщика (:func:`_pick`)."""
        return _pick(self)

    def _work(self) -> None:
        """Нитка кодировщика (:func:`_work`)."""
        _work(self)

    def _run(self, first: int, last: int) -> None:
        """Один заход кодировщика (:func:`_run`)."""
        _run(self, first, last)
