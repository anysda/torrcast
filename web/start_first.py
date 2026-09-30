"""Приговор полки ждёт, пока идёт подъём показа: раздачу первым получает зритель.

Приговор «играет ли» читает метаданные раздачи тем же TorrServer, что и запуск показа
(:mod:`web.shelf_playable`). Холодная полка судит плитки с первых секунд, и клик в эти
секунды делил стенд с ними: подготовка «Интерстеллара» шла 19.9 с вместо 5.0 с, а в
другом заходе не дождалась метаданных за 60 с. Новый приговор поэтому не начинается,
пока подъём не дошёл до кадра или не кончился отказом (:data:`~torrcast.usecases.
start_progress.START`); уже идущий доходит сам. Ожидание ограничено: застрявший подъём
не вправе остановить полку навсегда.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from typing import Final

from torrcast.domain.json_value import JsonValue
from torrcast.usecases.start_progress import START

#: Дольше приговор не ждёт: метаданные подъёма ждут 60 с, поиск перед ними - до 10 с.
WITHIN: Final = 90.0
#: Как часто спрашивать, кончился ли подъём.
STEP: Final = 0.5


def start_first(
    seen: Callable[[], dict[str, JsonValue] | None] = START.seen,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Вернуться, когда подъёма показа нет или ждать уже хватит."""
    ends = clock() + WITHIN
    while seen() is not None and clock() < ends:
        sleep(STEP)


__all__ = ["STEP", "WITHIN", "start_first"]
