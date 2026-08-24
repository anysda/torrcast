"""Сторож показа: кладёт позицию приёмника в состояние и отмечает досмотренное.
Заводит его цикл юнита (:func:`torrcast.usecases.worker._cmd_worker`).
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from torrcast.domain.entry import Entry
from torrcast.ports.state_store.slot import store
from torrcast.usecases.rank._hms import _hms

__all__ = ["WATCH_SECONDS", "Watch"]

#: Как часто сторож кладёт позицию в state, секунды.
WATCH_SECONDS = 10.0


@dataclass(slots=True)
class Watch:
    """Сторож: раз в :data:`WATCH_SECONDS` кладёт позицию приёмника в state.

    Позиция приходит абсолютной: манифест описывает весь фильм, а ``-copyts`` оставляет
    в сегментах исходные метки времени, поэтому приёмник считает время от начала фильма
    независимо от того, с какого места идёт упаковка. Пересчитывать смещение показу
    больше не нужно — раньше это была отдельная строчка возможной лжи. Про конец показа и
    стык серий - :meth:`close`.
    """

    key: str
    entry: Entry
    every: float = WATCH_SECONDS
    done: bool = False
    sealed: bool = False  # «досмотрено» уже легло на диск - тиками не переписываем
    seen: bool = False  # приёмник назвал живую позицию: без этого досмотра не бывает
    last: float = field(default_factory=time.monotonic)

    def see(self, pos: float) -> None:
        """Позиция; на диск не чаще раза в ``every`` с. Порога перехода тут нет."""
        if pos <= 0:  # приёмник ещё не начал считать - нулём позицию не затираем
            return
        self.entry.pos, self.seen = pos, True
        if time.monotonic() - self.last >= self.every:
            self.flush()

    def close(self) -> None:
        """Конец сеанса: картина доиграна - «досмотрено», а сериалу следующая серия.

        🔴 Путь перехода один и привязан к концу потока, а не к доле длительности. Терять
        его нельзя ни при каком поведении приёмника, поэтому «конец» опознаётся щедро
        (:attr:`torrcast.domain.entry.Entry.ending`). И ни при каком раскладе - показу, которого не
        было: закладка у конца плюс сдохший источник дают сеанс без единого LOAD, и фильм
        помечался досмотренным, не показав ни кадра. Отсюда :attr:`seen`.
        """
        if not self.sealed and self.seen and self.entry.ending:
            self.entry.pos = self.entry.dur
            self.done = True
        self.flush()

    def flush(self) -> None:
        """Записать состояние атомарно (tmp + rename в
        :mod:`torrcast.adapters.filesystem.state`).
        """
        if self.sealed:  # досмотренную запись повторными тиками не портим
            return
        self.last = time.monotonic()
        keeper = store()
        state = keeper.load()  # перечитываем: рядом мог писать другой ход
        state.put(self.key, self.entry.advance() if self.done else self.entry)
        keeper.save(state)
        if self.done:
            self.sealed = True
            what = f" {self.entry.label}" if self.entry.label else ""
            print(f"досмотрено{what}: {_hms(self.entry.pos)} из {_hms(self.entry.dur)}", flush=True)
