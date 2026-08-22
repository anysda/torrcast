"""Два числа о запасе показа: докуда обеспечено подряд и сколько это весит в памяти.

Спрашивают их сторож приёмника и журнал (:mod:`torrcast.usecases.feed_pack.feed`).
"""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.feed_pack.feed_segment import _have

if TYPE_CHECKING:
    from torrcast.usecases.feed_pack.feed_state import _State


def _front(state: _State, played: float = 0.0) -> float:
    """Докуда показ обеспечен **подряд** от позиции ``played``, секунды от начала фильма.

    Разница между этим числом и позицией приёмника — весь запас показа. Он и есть
    предмет всей возни с подвисами: пока запас положителен, приёмнику есть что взять, а
    как только он сходит в ноль — приёмник встаёт в BUFFERING. На этом числе стоит
    сторож приёмника: неподвижный BUFFERING при живом запасе — зависание и лечится
    нуджем, при пустом — законное ожидание нас и лечится упаковкой.

    ⚠️ Раньше здесь стоял глоб каталога (``Packer.frontier``), и после перемотки назад
    он врал в разы: в каталоге показа лежат честные куски прошлых прогонов (сетка
    детерминирована), и «докуда упаковано» считалось по ним. Замер на живом
    Q70D: откат с 40-й минуты на 10-ю — «показ 600 · упаковано 2010 ·
    впереди 1410 с», при том что перед приёмником не было ни одного куска. Запас,
    посчитанный за тысячу секунд от места, где показа нет, — это разрешение сторожу
    дёргать приёмник ровно тогда, когда дёргать нельзя.

    Правда считается от приёмника и только по фактам: кусок под позицией и цепочка
    за ним. Разрыв цепочки — конец запаса, что бы ни лежало дальше: перепрыгнуть
    дырку приёмник всё равно не сможет. Куска под позицией нет вовсе — запаса ноль.
    """
    slot = state.grid.slot_at(played)
    if not _have(state, slot):
        return played
    while slot + 1 < state.grid.count and _have(state, slot + 1):
        slot += 1
    return state.grid.end(slot)


def _weight(state: _State) -> int:
    """Сколько байт лежит в tmpfs прямо сейчас (рост без предела недопустим, а это
    единственный способ увидеть пик своими глазами).

    Считается и окно показа, и несданное каталога прогона (:meth:`Packer.pending`):
    память одна на оба, и вторая половина росла невидимой ровно потому, что число
    называло только первую.
    """
    total = 0
    for path in _state.segment_paths(state.out):
        with contextlib.suppress(OSError):  # вычистило окном прямо сейчас
            total += path.stat().st_size
    if not state.lock.acquire(blocking=False):
        return total
    try:
        return total + (0 if state.packer is None else state.packer.pending())
    finally:
        state.lock.release()
