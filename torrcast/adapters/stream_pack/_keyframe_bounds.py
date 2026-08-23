"""Считает границы сетки по опорным кадрам; правило целиком - в :meth:`Grid.on_keyframes`."""

from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

from torrcast.adapters.stream_pack.weigher import weigher

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _keyframe_bounds(
    keys: Sequence[float],
    duration: float,
    step: float,
    sizes: Sequence[int],
    extra_mbit: float,
    ceiling_mbit: float,
    cap: float,
    fixed_mbit: float,
    *,
    fill_from: float = 0.0,
    span_cap: float = 0.0,
) -> tuple[tuple[float, ...], Callable[[float, float], float] | None]:
    """Границы сегментов и предсказатель веса КОПИИ для :meth:`Grid.on_keyframes`.

    Счёт лежит отдельно от правила, которое он считает: разбор правила - потолок байт,
    потолок длины, ближайшая голова, короткий хвост - остался докстрокой своего метода.
    """

    # Потолок длины судит кандидата ровно так же, как потолок веса: годен - и точка.
    def short(prev: float, key: float) -> bool:
        return span_cap <= 0.0 or key - prev <= span_cap

    weigh = weigher(keys, sizes, extra_mbit, ceiling_mbit, fixed_mbit)
    # Отдельно от границ - вес КОПИИ (без потолков): тяжёлый кусок режется сеткой и
    # уезжает на ТВ перекодом, а на диск прогрев кладёт сначала его самого, во весь
    # вес. Бюджет прогрева проверяется именно под этот, пиковый, вес.
    copy = (
        weigher(keys, sizes, extra_mbit, 0.0)
        if len(sizes) == len(keys) and len(keys) >= 2
        else None
    )
    bounds = [0.0]
    limit = duration - step / 2
    index = 0
    while True:
        prev = bounds[-1]
        index = bisect.bisect_right(keys, prev, lo=index)
        fits = before = first = None
        filling = False
        for key in keys[index:]:
            if key >= limit:
                break
            if weigh(prev, key) <= cap and short(prev, key):
                fits = key
            if key >= prev + step:
                if first is None:
                    first = key
                    filling = fill_from > 0 and weigh(prev, key) > fill_from
                if not filling or weigh(prev, key) > cap or not short(prev, key):
                    break
            if key - prev >= step / 2 and weigh(prev, key) <= cap:
                before = key
        if first is None:
            if weigh(prev, duration) <= cap:
                break  # короткий хвост влезает и по-прежнему прилипает к последнему
            tail = [key for key in keys[index:] if prev < key < duration]
            tail_fits = [key for key in tail if weigh(prev, key) <= cap and short(prev, key)]
            if not tail:
                break  # последний GOP тяжелее потолка, резать его нечем
            bounds.append(tail_fits[-1] if tail_fits else tail[0])
            continue
        first_fits = weigh(prev, first) <= cap and short(prev, first)
        nearest_head = (
            len(bounds) <= 2
            and before is not None
            and first_fits
            and prev + step - before < first - prev - step
        )
        if nearest_head:
            assert before is not None  # условие nearest_head уже доказало границу
            bounds.append(before)
        elif filling and fits is not None:
            bounds.append(fits)
        elif first_fits or fits is None:
            bounds.append(first)  # влез - или один GOP тяжелее потолка, резать нечем
        else:
            bounds.append(fits)
    return tuple(bounds), copy
