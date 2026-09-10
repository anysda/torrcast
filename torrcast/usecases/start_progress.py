"""Ход подъёма показа наружу: сколько ещё ждать картинку и который источник в работе.

Слот один на процесс, и другого места у этих двоих нет: подъём идёт в ГЛАВНОМ потоке
(:meth:`hass.orders.Orders.run_one`), а спрашивает его страница из потока розетки
(``GET /api/state``), пока экран показывает подготовку.

🔴 Срок наружу идёт ИЗМЕРЕННЫЙ, а не бюджетный. Бюджет старта
(:data:`torrcast.usecases.start_budget.START_BUDGET`) - сумма потолков всех фаз, то есть
минуты; назвать его зрителю значило бы соврать в разы на каждом обычном показе. Поэтому
слот помнит, сколько шли последние подъёмы ЭТОЙ машины, и отвечает их серединой.
Замеров меньше :data:`ENOUGH` - срока нет вовсе, и страница молчит о нём
(:mod:`web.static.player-screens`), а не рисует выдумку с точностью до секунды.

🔴 Кончившийся срок - это «больше не знаю», а не ноль: названная секунда прошла, а
картинки нет, и держать на экране «начнётся через ~0 с» значит врать дальше. Слот в
такую минуту отвечает сроком ``None``, и полоса возвращается к бегущей.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from statistics import median
from typing import Final

from torrcast.domain.json_value import JsonValue

#: Сколько последних подъёмов помнить. Пять - это память об одном вечере: машина, рой и
#: сеть за него не меняются, а старые замеры к сегодняшнему показу отношения не имеют.
KEPT: Final = 5

#: Со скольких замеров срок вообще называется. Один замер - это не разброс, а случай:
#: живой прогон 10-09-2026 назвал по единственному подъёму «starts in ~56 s» там, где
#: картинка пришла за 20 с (ошибка в 2.8 раза), а следующий срок, взятый уже из двух
#: замеров, назвал 40 с при фактических 40.5 с. Дешевле промолчать один показ, чем
#: соврать втрое: молчащий срок страница переживает, она просто не рисует строку.
ENOUGH: Final = 2


class StartProgress:
    """Что подъём показа знает о себе прямо сейчас и сколько шли прошлые подъёмы."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._began: float | None = None
        self._source: tuple[int, int] = (0, 0)
        self._measured: list[float] = []

    def began(self) -> None:
        """Подъём пошёл: часы ожидания с нуля, источник ещё не назван."""
        with self._lock:
            self._began = self._clock()
            self._source = (0, 0)

    def source(self, number: int, total: int) -> None:
        """Какой источник очереди сейчас спрашивают и сколько их всего."""
        with self._lock:
            self._source = (number, total)

    def landed(self, seconds: float) -> None:
        """Картинка на экране за ``seconds``: замер идёт в память, ожидание кончилось."""
        with self._lock:
            self._measured.append(seconds)
            del self._measured[:-KEPT]
            self._began = None
            self._source = (0, 0)

    def gone(self) -> None:
        """Подъёма больше нет (отказ, остановка, отмена): замерять нечего."""
        with self._lock:
            self._began = None
            self._source = (0, 0)

    def seen(self) -> dict[str, JsonValue] | None:
        """Снимок ожидания для ``GET /api/state``; подъёма нет - ``None``."""
        with self._lock:
            if self._began is None:
                return None
            waited = self._clock() - self._began
            number, total = self._source
            known = len(self._measured) >= ENOUGH
            left = (median(self._measured) - waited) if known else 0.0
        return {
            "waited": round(waited, 1),
            "left": round(left) if left > 0 else None,
            "source": number or None,
            "sources": total or None,
        }


#: Подъём этого процесса. Заводить второй незачем: показ на машине один.
START: Final = StartProgress()

__all__ = ["ENOUGH", "KEPT", "START", "StartProgress"]
