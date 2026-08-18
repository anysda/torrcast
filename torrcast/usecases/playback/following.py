"""Чем прогреву заняться, когда серия ляжет на диск целиком.

Кладёт эту ручку показу юнит (:func:`torrcast.usecases.worker._cmd_worker`), а зовёт её
сам прогрев - ровно один раз за серию.
"""

from __future__ import annotations

from typing import Protocol

from torrcast.usecases.warm import Warmer


class Following(Protocol):
    """Прогрев СЛЕДУЮЩЕЙ серии, собранный лениво: ``None`` - греть больше нечего."""

    def __call__(self) -> Warmer | None:
        """Собрать прогрев следующей серии; ``None`` - фильм или последняя серия."""
