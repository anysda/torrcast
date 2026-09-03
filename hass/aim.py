"""Место закладки, названное собственной перемоткой моста, пока она приземляется.

Ползунок карточки обязан уехать туда, куда его поставили, в ту же секунду. Запись
показа этого места ещё не знает: сторож кладёт закладку на диск раз в
:data:`torrcast.usecases.watch.WATCH_SECONDS`, а Home Assistant переспрашивает состояние
сразу после команды (``custom_components/torrcast/coordinator.py``,
``async_request_refresh``) - и на том опросе мост отвечал СТАРЫМ местом, отбрасывая
ползунок назад. Отсюда защёлка, ровно та же, что у слова о паузе
(:class:`hass.motion.Motion`), и снимает её так же факт, а не таймер вслепую.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import replace

from torrcast.domain.playback_snapshot import PlaybackSnapshot
from torrcast.usecases.watch import WATCH_SECONDS

#: Сколько защёлка места держится против записи показа, секунды.
#:
#: Слово о паузе показ кладёт в запись НА ПЕРЕХОДЕ и сбрасывает на диск сразу, поэтому
#: ему хватает :data:`hass.motion.TOOK_SECONDS`. У закладки такого перехода нет: её
#: кладёт сторож раз в :data:`~torrcast.usecases.watch.WATCH_SECONDS` (10 с), и про
#: состоявшуюся перемотку запись узнаёт на ближайшем таком тике. Запас сверх тика - круг
#: опроса приёмника показом. Окно вышло, а закладка так и стоит у прежнего места -
#: приёмник команду не взял, и ползунок возвращается к правде.
LANDED_SECONDS = WATCH_SECONDS + 4.0


class Aim:
    """Место, названное перемоткой моста; правду возвращает факт записи либо окно.

    Меряется по опросам того, кто спрашивает: каждый ``GET /api/state`` - и замер
    правды (:meth:`seen` запоминает, где стоит закладка), и ответ карточке.
    """

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        #: Где стояла закладка на последнем опросе: от неё Home Assistant и считал сдвиг.
        self._seen: tuple[str, float] = ("", 0.0)
        self._key = ""
        self._from = 0.0
        self._to = 0.0
        self._at = -1.0

    def at(self, offset: float) -> None:
        """Мост послал ``seekby``: закладка с этой секунды считается на новом месте.

        Цель собирается обратно из сдвига, а не выдумывается: Home Assistant считает
        ``seekby`` от той же позиции снимка, которую он в этот миг рисует на карточке
        (``async_media_seek``), и ``позиция + сдвиг`` - ровно та точка, куда человек
        отпустил ползунок. Отрицательный ноль оси тут невозможен: показ до начала
        картины не мотают.
        """
        self._key, self._from = self._seen
        self._to = max(0.0, self._from + offset)
        self._at = self._clock()

    def seen(self, shown: PlaybackSnapshot | None) -> PlaybackSnapshot | None:
        """Снимок для карточки: место защёлки, пока перемотка не доехала до записи."""
        if shown is None:
            return None
        self._seen = (shown.key, shown.position)
        place = self._place(shown)
        return shown if place is None else replace(shown, position=place)

    def _place(self, shown: PlaybackSnapshot) -> float | None:
        """Место защёлки, либо ``None`` - правду отдавать уже пора.

        Чужой показ защёлку не наследует: сменился ключ - оптимизма нет. Дальше решает
        факт: запись назвала место ближе к цели, чем к тому, откуда мотали, - перемотка
        состоялась, и правда точнее выдумки. Не назвала за целое окно - приёмник
        команду не взял.
        """
        if self._at < 0.0 or shown.key != self._key:
            self._at = -1.0
            return None
        gone = self._clock() - self._at
        if gone >= LANDED_SECONDS or self._landed(shown.position):
            self._at = -1.0
            return None
        # Показ едет и под защёлкой: ответить одним и тем же числом на два опроса
        # значило бы отбросить ползунок назад на весь промежуток между ними - фронт
        # доводит его сам от метки снимка, и метка эта у каждого ответа своя.
        return self._to + (0.0 if shown.paused == "PAUSED" else gone)

    def _landed(self, position: float) -> bool:
        """Закладка ближе к цели, чем к месту, откуда мотали: перемотка доехала."""
        return abs(position - self._to) < abs(position - self._from)
