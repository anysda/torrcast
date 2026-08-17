"""Дочитал ли прогон вход до конца и что он нарезал на самом деле.

Спрашивают отсюда выкладка и горячий путь показа (:mod:`torrcast.usecases.feed_pack`).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.hls_settings import PACK_LIST, PACK_SHORT_SECONDS
from torrcast.usecases.feed_pack._segment_files import _names

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack._state import Grid
    from torrcast.usecases.feed_pack.packer_state import _State


def _finished(state: _State) -> bool:
    """Прогон дочитал вход до конца - а не просто вышел из процесса.

    🔴 Ноль от ffmpeg этого не доказывает. Вход, умерший на середине, ffmpeg
    отмечает строкой ``Error during demuxing: Input/output error`` - и **выходит
    нулём**. Замер: 108 обрывов на 108 местах файла, ноль вышел 4 раза, и трижды
    последний кусок оказался дописан не до конца. На одном и том же месте исход не
    повторяется - это гонка между концом чтения и концом записи, поэтому редкость
    тут ничего не значит: по одному коду возврата обрезок (замер: от нуля до 9.4 с
    вместо обещанных 10) уезжает зрителю как готовый кусок, тихо и без единой жалобы
    в журнале. А оборванный файл - вход не рвётся, а кончается - даёт ноль всегда:
    12 прогонов из 12.

    Поэтому спрашивается не код, а обещание сетки. Где кончился последний кусок,
    говорит сам ffmpeg в своём списке нарезки (:func:`_cuts`); где он обязан был
    кончиться - :meth:`Grid.end`. Недобор больше :data:`PACK_SHORT_SECONDS` - прогон
    оборвался, каким бы кодом он ни вышел.

    Куски за пределом захода (:attr:`last`) в счёт не идут: заход кодировщика
    ограничен ``-to`` с запасом в секунду, и огрызок за этим пределом короче своего
    места по замыслу, а не по аварии.

    Считается один раз на прогон: у мёртвого процесса ни файлы, ни список уже не
    меняются, а спрашивают отсюда и выкладка, и горячий путь показа.
    """
    if state.whole is None:
        if state.proc.poll() != 0:
            return False
        state.whole = _reached(state)
    return state.whole


def _reached(state: _State) -> bool:
    grid = state.grid
    if grid is None:
        return True
    mine = [
        slot
        for slot in map(_state.segment_slot, _names(state.run))
        if slot >= 0 and (state.last < 0 or slot <= state.last)
    ]
    if not mine:
        return True  # прогон не написал ни одного своего куска - обрываться нечему
    tail = max(mine)
    ends = {slot: end for slot, _began, end in _cuts(state)}
    if tail not in ends:
        # Кусок закрыт, а строки о нём нет: список ведёт тот же ffmpeg и пишет её
        # ровно на закрытии (``-segment_list_flags +live``). Верить тут нечему.
        return False
    return ends[tail] >= grid.end(tail) - PACK_SHORT_SECONDS


def _cuts(state: _State) -> list[tuple[int, float, float]]:
    """Что ffmpeg нарезал на самом деле: ``(сегмент, начало, конец)`` по его же списку.

    Нужно ровно для одного: сверить факт с манифестом (:func:`_drift`). Первую строку
    списка приходится пропускать — в ней ffmpeg пишет начало прогона нулём.
    """
    found: list[tuple[int, float, float]] = []
    try:
        text = (state.run / PACK_LIST).read_text("utf-8", "replace")
    except OSError:
        return found
    for line in text.splitlines():
        parts = line.strip().rstrip(",").split(",")
        if len(parts) < 3:
            continue
        slot = _state.segment_slot(parts[0].rsplit("/", 1)[-1])
        with contextlib.suppress(ValueError):
            found.append((slot, float(parts[1]), float(parts[2])))
    return found


def _drift(state: _State, grid: Grid) -> float:
    """Насколько нарезанное разошлось с обещанным в манифесте, секунды.

    Ноль (точнее, доли кадра) — манифест не врёт: ``EXTINF`` совпадает с фактом.
    Больше кадра — повод не верить нарезке и сказать об этом в журнал: значит, карта
    опорных кадров разошлась с потоком.

    Начало ленты (:attr:`torrcast.stream.Grid.origin`) вычитается: ffmpeg пишет в свой
    список уже сдвинутые метки, и без этого вычитания «расхождение с манифестом» на
    каждом фильме с B-кадрами показывало бы ровно этот сдвиг вместо нуля.
    """
    worst = 0.0
    for slot, began, _ in _cuts(state)[1:]:
        if slot >= state.first:
            worst = max(worst, abs(began - grid.origin - grid.start(slot)))
    return worst
