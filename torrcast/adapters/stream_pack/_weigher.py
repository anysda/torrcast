"""Предсказывает вес куска по карте опорных кадров; по нему сетка держит потолок байт."""

from __future__ import annotations

import bisect
from typing import TYPE_CHECKING

from torrcast.domain.hls_settings import SPLIT_SLACK

if TYPE_CHECKING:
    from collections.abc import Callable, Sequence


def _weigher(
    keys: Sequence[float],
    sizes: Sequence[int],
    extra_mbit: float,
    ceiling_mbit: float,
    fixed_mbit: float = 0.0,
) -> Callable[[float, float], float]:
    """Предсказатель веса куска ``[a, b)`` в байтах — тот же расчёт, что у профиля тяжести.

    Карта даёт байты **контейнера**: у «Моаны 2» это десять озвучек и восемь субтитров
    сверх картинки. На ТВ уезжает видео плюс наш AAC, поэтому из битрейта вычитается
    ``extra_mbit`` (:class:`torrcast.recode.Weights` считает ту же поправку), а тяжёлый
    кусок ещё и перекодируется — выше ``ceiling_mbit`` он не уедет при всём желании.

    Карты смещений нет — вес неизвестен, и предсказатель честно отдаёт ноль: правило
    потолка тогда не срабатывает ни разу, а сетка остаётся прежней.

    ``fixed_mbit`` карту не спрашивает вообще: при сплошном перекоде вес куска задаём
    мы сами, и вес источника к нему отношения не имеет. 🔴 Замер на живом Q70D
    (TC-29, «Bocchi the Rock» 1.3 Мбит/с HEVC): сетка поверила карте, поставила куски
    по 15-20 с, а перекод положил в них 18.3 и 21.4 МБ — при потолке 16 и замеренной
    границе срыва 19.4.
    """
    if fixed_mbit > 0:
        return lambda a, b: max(0.0, b - a) * fixed_mbit * 1e6 / 8
    if len(sizes) != len(keys) or len(keys) < 2:
        return lambda a, b: 0.0

    def weigh(a: float, b: float) -> float:
        span = b - a
        if span <= 0:
            return 0.0
        head = bisect.bisect_right(keys, a + SPLIT_SLACK) - 1
        tail = bisect.bisect_right(keys, b + SPLIT_SLACK) - 1
        head = min(max(head, 0), len(sizes) - 1)
        tail = min(max(tail, 0), len(sizes) - 1)
        mbit = max(0.0, (sizes[tail] - sizes[head]) * 8 / span / 1e6 - extra_mbit)
        if ceiling_mbit > 0:
            mbit = min(mbit, ceiling_mbit)
        return mbit * span * 1e6 / 8

    return weigh
