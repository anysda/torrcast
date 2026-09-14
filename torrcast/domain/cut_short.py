"""Урезанный круг: опорный источник отдал ноль не потому, что раздач нет, а потому что сдался.

Переходник JacRed (``scripts/jacred-indexer.py``) ждёт свой API :data:`ADAPTER_CUT` секунд и
на молчание отвечает Prowlarr пустым списком, а не разрывом: разрыв Prowlarr наказывает
лестницей банов. Для круга такой ноль неотличим от честного, и «Тачки» с 4 раздачами вместо
32 помнились пять минут как полный круг. Отличает его время: честный ноль приходит быстро,
а ноль переходника - не раньше его отсечки.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Final

from torrcast.domain.wait_indexer import wait_indexer

#: Сколько секунд переходник JacRed ждёт свой API; равна ``TIMEOUT`` переходника.
ADAPTER_CUT: Final = 5.0


def cut_short(counts: Mapping[str, int], spent: Mapping[str, int]) -> tuple[str, ...]:
    """Опорные источники круга, чей ноль пришёл не раньше отсечки переходника."""
    return tuple(
        name
        for name, rows in counts.items()
        if rows == 0 and wait_indexer(name) and spent.get(name, 0) >= ADAPTER_CUT * 1000
    )


__all__ = ["ADAPTER_CUT", "cut_short"]
