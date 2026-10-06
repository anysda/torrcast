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

from torrcast.domain.json_value import JsonValue
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
#:
#: 🔴 Тик - не весь срок: после перемотки ТВ буферизует до 26 с, и запись называет новое
#: место через 19-21 с (живой приёмник 06-10-2026). Окно в 14 с отдавало ползунок и
#: вкладку на ТВ записи, ещё стоящей у прежнего места.
LANDED_SECONDS = WATCH_SECONDS + 26.0 + 4.0

#: Дальше этого от места защёлки запись ещё не приземлилась, секунды. Нажатия подряд
#: показ берёт и двумя перемотками (``seekby -240``, следом ``-60``), и запись успевает
#: назвать первую: 1236.5 при цели 1161.2 ближе к цели, чем к 1460, но это не она.
#: Ошибка самой цели - отставание правды на нажатии, до тика записи (замер: 0.7 и 7.2 с).
NEAR_SECONDS = WATCH_SECONDS + 5.0


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
        #: Сколько перемоток моста было: номер новой меняется, и вкладка на ТВ узнаёт о ней
        #: из снимка, а не только из своего нажатия (:meth:`sought`).
        self._n = 0
        self._paused = False

    def at(self, offset: float) -> None:
        """Мост послал ``seekby``: закладка с этой секунды считается на новом месте.

        Цель собирается обратно из сдвига, а не выдумывается: Home Assistant считает
        ``seekby`` от той же позиции снимка, которую он в этот миг рисует на карточке
        (``async_media_seek``), и ``позиция + сдвиг`` - ровно та точка, куда человек
        отпустил ползунок. Отрицательный ноль оси тут невозможен: показ до начала
        картины не мотают.
        """
        key, truth = self._seen
        # Нажатие поверх неприземлившейся перемотки считается от её цели, как и сдвиг у
        # Home Assistant: 3x60 подряд - это +180, а не +60 от прежней правды (TC-1169).
        held = self._held(key)
        self._key, self._from = key, truth
        self._to = max(0.0, (truth if held is None else held) + offset)
        self._at = self._clock()
        self._n += 1

    def _held(self, key: str) -> float | None:
        """Место живой защёлки этого показа, либо ``None``."""
        gone = self._clock() - self._at
        if self._at < 0.0 or key != self._key or gone >= LANDED_SECONDS:
            return None
        return self._to + (0.0 if self._paused else gone)

    def sought(self, shown: PlaybackSnapshot | None) -> dict[str, JsonValue] | None:
        """Последняя перемотка моста этого показа: её номер и цель; не было - ``None``.

        🔴 Плёнка вкладки на ТВ назад за докладом не ходит (``player.js``, ``_follow``), и
        перемотка назад, нажатая НЕ в ней (карточка, Home Assistant, ``/api/control``),
        оставляла её на старом месте, пока ТВ играл новое (TC-1169, живой приёмник
        06-10-2026: ТВ ушёл на 745.1, плёнка осталась на 1062). Номер живёт и после
        приземления: опрос вкладки мог пропустить саму защёлку.
        """
        if shown is None or not self._n or shown.key != self._key:
            return None
        return {"n": self._n, "to": round(self._to, 1)}

    def seen(self, shown: PlaybackSnapshot | None) -> PlaybackSnapshot | None:
        """Снимок для карточки: место защёлки, пока перемотка не доехала до записи."""
        if shown is None:
            return None
        self._seen = (shown.key, shown.position)
        self._paused = shown.paused == "PAUSED"
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
        # Показ едет и под защёлкой: ответить одним и тем же числом на два опроса
        # значило бы отбросить ползунок назад на весь промежуток между ними - фронт
        # доводит его сам от метки снимка, и метка эта у каждого ответа своя.
        place = self._to + (0.0 if shown.paused == "PAUSED" else gone)
        if gone >= LANDED_SECONDS or self._landed(shown.position, place):
            self._at = -1.0
            return None
        return place

    def _landed(self, position: float, place: float) -> bool:
        """Закладка у места защёлки и ближе к цели, чем к месту, откуда мотали."""
        near = abs(position - place) <= NEAR_SECONDS
        return near and abs(position - self._to) < abs(position - self._from)
