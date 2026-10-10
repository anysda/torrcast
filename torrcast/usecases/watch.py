"""Сторож показа: кладёт позицию приёмника в состояние и отмечает досмотренное.
Заводит его цикл юнита (:func:`torrcast.usecases.worker._cmd_worker`).
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field

from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.entry import Entry
from torrcast.ports.state_store.slot import store
from torrcast.usecases.rank._hms import _hms

__all__ = ["NEXT_LOOKAHEAD", "SEEK_SECONDS", "WATCH_SECONDS", "Watch"]

#: Как часто сторож кладёт позицию в state, секунды.
WATCH_SECONDS = 10.0
#: Скачок места между опросами дальше этого - перемотка, и на диск она уходит сразу, секунды.
#:
#: Тика ей мало: по записи защёлка карточки (:mod:`hass.aim`) узнаёт, что перемотка
#: приземлилась. Стенд 06-10-2026, ``-240`` от 131.0 к нулю: ТВ стоял на 0.0 (ноль запись
#: не берёт), заиграл с 2.9 через 20 с, и до тика защёлка считала место по своим часам -
#: следующий ``+60`` карточка взяла от 30, а показ от 8.8.
SEEK_SECONDS = 15.0
NEXT_LOOKAHEAD = 25.0


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
    #: Показ закрыл зритель с пульта (:func:`torrcast.usecases.revive_playback._closed._closed`).
    #: Закладка при этом двигается как обычно, а вот следующую серию цикл (:mod:`torrcast.
    #: usecases.worker_loop`) на приёмнике не поднимает - сеанс кончается на месте (TC-880).
    closed_by_remote: bool = False
    #: Сеанс оборвался у конца без отданного хвоста (:meth:`cut`): это не «досмотрено».
    cut_short: bool = False
    #: One deferred search at a torrent boundary; it must never hold up receiver polling.
    nearing_end: Callable[[], None] | None = None
    _near_called: bool = False
    last: float = field(default_factory=time.monotonic)
    #: Последняя позиция, названная сторожу в этом сеансе: от неё видна перемотка.
    heard: float = -1.0

    def see(self, pos: float) -> None:
        """Позиция; на диск не чаще раза в ``every`` с. Порога перехода тут нет."""
        if pos <= 0:  # приёмник ещё не начал считать - нулём позицию не затираем
            return
        self.entry.pos, self.entry.moved = pos, True
        jumped, self.heard = self.heard >= 0.0 and abs(pos - self.heard) > SEEK_SECONDS, pos
        if (
            not self._near_called
            and self.nearing_end is not None
            and self.entry.dur - pos <= NEXT_LOOKAHEAD
        ):
            self._near_called = True
            self.nearing_end()
        if jumped or time.monotonic() - self.last >= self.every:
            self.flush()

    def skip_to(self, pos: float) -> None:
        """Сохранить место за намеренно пропущенным куском, не выдавая его за показанный кадр."""
        if pos <= self.entry.pos:
            return  # приёмник уже дошёл дальше сам - перешагивание его назад не откатывает
        self.entry.pos = pos
        self.flush()  # решение необратимо для сеанса и обязано пережить его внезапную смерть

    def cut(self, why: str) -> None:
        """Хвост картины не отдан, а сеанс кончается: сказать вслух и оставить отметку темноты.

        Отметка (:attr:`torrcast.domain.entry.Entry.dark`) переживает юнит, и по ней
        бухгалтерия досмотра (:func:`_account_watched`) не засчитывает закладку у конца.
        """
        self.cut_short = True
        self.entry.dark = self.entry.dark or time.time()
        self.entry.dark_why = why
        print(why, flush=True)

    def close(self) -> None:
        """Конец сеанса: картина доиграна - «досмотрено», а сериалу следующая серия.

        🔴 Путь перехода один и привязан к концу потока, а не к доле длительности. Терять
        его нельзя ни при каком поведении приёмника, поэтому «конец» опознаётся щедро
        (:attr:`torrcast.domain.entry.Entry.ending`). И ни при каком раскладе - показу, которого не
        было: закладка у конца плюс сдохший источник дают сеанс без единого LOAD, и фильм
        помечался досмотренным, не показав ни кадра. Отсюда
        :attr:`torrcast.domain._playing._Playing.moved`.
        """
        if not self.sealed and self.entry.moved and self.entry.ending and not self.cut_short:
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
            pos, duration = _hms(self.entry.pos), _hms(self.entry.dur)
            print(phrase("watch.finished", what=what, pos=pos, duration=duration), flush=True)
