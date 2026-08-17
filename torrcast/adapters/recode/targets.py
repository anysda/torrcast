"""Слоты, которые обязан взять кодировщик: тяжёлые или слишком увесистые.

Зовёт их :attr:`torrcast.adapters.recode.recoder_state._State.targets`."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from torrcast.adapters._legacy_stream_types import Grid
    from torrcast.adapters.recode.weights import Weights


def _targets(weights: Weights, grid: Grid, threshold: float, cap: int) -> tuple[int, ...]:
    """Слоты, которые обязан взять кодировщик: тяжёлые **или** слишком увесистые.

    Две мерки, и они не совпадают. Первая — битрейт: приёмник не тянет
    ``threshold`` Мбит/с и выше как есть. Вторая — вес куска: сегмент тяжелее
    :attr:`cap` роняет приёмник независимо от битрейта,
    а такой кусок бывает и на скромных 12 Мбит/с, если он длинный. Замер по
    картам: «Моана» 2016 — лёгкое кино, тяжёлых кусков нет вовсе, а увесистых семь,
    самый большой 18.3 МБ при замеренной границе срыва 19.4 МБ.
    """
    heavy = weights.heavy(threshold)
    bulky = weights.bulky(grid, cap)
    return heavy if not bulky else tuple(sorted(set(heavy) | set(bulky)))
