"""Ответ на запрос сегмента: файл окна показа, прогретое с диска или честное «не будет».

Зовут отсюда потоки раздачи (:meth:`torrcast.usecases.feed_pack.feed.Feed.segment`).
"""

from __future__ import annotations

import contextlib
import math
from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.usecases.warm.segment_start import segment_start
from torrcast.usecases.warm.settings import SKEW_MAX

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

    from torrcast.usecases.feed_pack.feed_state import _State


def _segment(state: _State, slot: int, steer: Callable[[int], bool]) -> Path | None:
    """Файл сегмента ``slot``; ``None`` — его не будет (за концом фильма или не успели).

    Зовётся из потоков раздачи, поэтому решение о перезапуске упаковки принимается
    под замком: после перемотки приёмник просит несколько сегментов одновременно, и
    перезапустить упаковку должен ровно первый из них.

    ⚠️ Замок берётся без ожидания. Внутри решения лежит пробный прогон
    (:func:`pack_start`), до минуты по потолку, и сосед, вставший в очередь за
    замком, всё это время не смотрел бы даже на свой файл: тот успевает появиться,
    а ответ уходит на минуту позже. Занятый замок значит ровно «решение уже
    принимают», и правильный ход тут - ждать файл, а не очередь.

    🔴 TC-622. Номер за границами сетки не идёт в разбирательство с упаковкой вовсе.
    Раздача открыта в сеть, и постучать в неё может кто угодно (сосед по адресу,
    второй сендер, ошибочный повтор); приёмник таких имён не просит, потому что
    манифест их не обещал. Раньше номер шёл в :meth:`_steer` как есть, а там
    :meth:`Grid.start` его **зажимает** в границы - и ``v99999`` получал место
    последнего сегмента фильма: упаковка перезапускалась с конца (живая приёмка
    TC-617: ``заход упаковки {слот: 99999, встали: 7778.899}``), да ещё и без резов,
    потому что ``-segment_times`` строится по ``range(slot + 1, grid.count)`` и для
    номера за сеткой пуст. Хуже того, поток раздачи с этим запросом возвращался сюда
    каждые 0.2 с все ``wait`` секунд: замер на сухом стенде - **61 перезапуск
    упаковки с одного GET**. Показ вставал насмерть и сам объявлял ``dark``.

    Ждать тут нечего по сетке, а не по краю прогона: этого имени в манифесте не было
    и не будет, поэтому ответ честен сразу и стоит ноль. Уже лежащий на диске кусок
    всё равно отдаётся файлом - чтение того, что есть, упаковку не двигает, и куски
    прошлых прогонов остаются честными.
    """
    path = state.out / _state.segment_name(slot)
    if not 0 <= slot < state.grid.count:
        return path if path.exists() else None
    deadline = _state.clock_port.monotonic() + state.wait
    while True:
        if path.exists():
            return path
        # Прогретое на диске равноценно живому куску: то же место фильма, то же имя,
        # та же сетка (:attr:`vault`). Проверка стоит ЗДЕСЬ, до всякого разбирательства
        # с упаковкой, и в этом весь смысл прогрева: перемотка в прогретую зону
        # отвечает файлом сразу, не поднимая ffmpeg и не спрашивая сеть.
        warm = _warm(state, slot)
        if warm is not None:
            return warm
        if state.lock.acquire(blocking=False):
            try:
                hope = steer(slot)
            finally:
                state.lock.release()
            if path.exists():
                return path
            if not hope:
                return None
        if _state.clock_port.monotonic() >= deadline:
            return None
        _state.clock_port.sleep(0.2)


def _warm(state: _State, slot: int) -> Path | None:
    """Прогретый на диске кусок этого места или ``None``.

    ⚠️ Прогретое идёт наружу мимо упаковки, а значит и мимо обоих мест, где вес куска
    зажат потолком приёмника (:meth:`Packer.publish`,
    :meth:`torrcast.adapters.recode.recoder.Recoder.holding`). Прогрев же кладёт фильм на диск
    копией, а тяжёлые места приводит к перекоду отдельным, ПОЗДНИМ заходом
    (:meth:`torrcast.usecases.warm.warmer.Warmer._spots_left`) - до него на месте тяжёлого куска
    лежит копия во весь свой вес.

    Замер, ради которого правило написано («Тачки» 2006, 1080p, 39% фильма тяжелее
    потолка): прогрев обгонял показ вчетверо, показ брал прогретые копии по 17-44 МБ,
    и приёмник вставал на каждой. 32 ``BUFFERING`` и 20 пинков за 14 минут, 31 кусок
    из 50 приёмник просил повторно, картинка шла вдвое медленнее реального времени.

    Поэтому кусок тяжелее потолка прогретым не считается: под ним живая упаковка,
    которая тот же кусок отдаст перекодом. Ждать перекод дольше, чем взять готовое с
    диска, - и это правильная цена: подгруз тут не «медленнее», а «не играет вовсе».
    """
    if state.vault is None:
        return None
    path: Path = state.vault.path(slot)
    if not path.exists():
        return None
    size = 0
    with contextlib.suppress(OSError):
        size = path.stat().st_size
    if size > state.cap:
        return None
    began = segment_start(path)
    want = state.grid.start(slot) + state.grid.origin
    if not math.isnan(began) and abs(began - want) <= SKEW_MAX:
        return path
    with contextlib.suppress(OSError):
        path.unlink(missing_ok=True)
    detail = "таймкод не прочитан" if math.isnan(began) else f"{began - want:+.2f} с"
    state._say(f"прогретый v{slot} мимо сетки ({detail}) - переделываю живой упаковкой")
    return None


def _have(state: _State, slot: int) -> bool:
    """Есть ли кусок этого места — всё равно, в окне показа или в прогретом."""
    return (state.out / _state.segment_name(slot)).exists() or _warm(state, slot) is not None
