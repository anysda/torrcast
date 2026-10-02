"""Пауза до следующей пересборки полок: час, а полке с недосчитанным индексером - раньше.

Индексер, который недосчитан на каждом проходе (медленный, но живой), иначе давал бы
пересборку каждые пять минут навечно: 12 в час по ~80 с работы (замер мержера на стенде,
TC-1322). Поэтому ранних пересборок подряд не больше :data:`EARLY_TIMES`, дальше - обычный
час; счёт начинается заново, когда проход собрал ленту без недосчёта.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

#: Сколько ранних пересборок подряд даётся недосчитанной ленте.
EARLY_TIMES: Final = 2


@dataclass
class RebuildPause:
    """Счётчик ранних пересборок подряд; ``after`` - пауза после очередного прохода."""

    every: float
    soon: float
    _early: int = 0

    def after(self, short: bool) -> float:
        """Пауза после прохода; ``short`` - лента прохода так и осталась недосчитанной."""
        self._early = self._early + 1 if short else 0
        return self.soon if 0 < self._early <= EARLY_TIMES else self.every


__all__ = ["EARLY_TIMES", "RebuildPause"]
