"""Чем прогреву заняться, когда серия ляжет на диск целиком.

Кладёт эту ручку показу юнит (:func:`torrcast.usecases.worker._cmd_worker`), а зовёт её
сам прогрев - ровно один раз за серию.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass, field
from typing import Protocol

from torrcast.usecases.warm.warmer import Warmer


class Following(Protocol):
    """Прогрев СЛЕДУЮЩЕЙ серии, собранный лениво: ``None`` - греть больше нечего."""

    def __call__(self) -> Warmer | None:
        """Собрать прогрев следующей серии; ``None`` - фильм или последняя серия."""


@dataclass(slots=True)
class _PreparedFollowing:
    """Собрать следующий прогрев после первого кадра, не задерживая стык серий."""

    make: Following
    _done: threading.Event = field(default_factory=threading.Event)
    _thread: threading.Thread | None = None
    _value: Warmer | None = None
    _error: Exception | None = None

    def start(self) -> None:
        """Начать подготовку один раз; повторный первый кадр второй нити не создаёт."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._prepare, daemon=True, name="torrcast-follow")
        self._thread.start()

    def __call__(self) -> Warmer | None:
        """Отдать подготовленный прогрев или честно передать сбой цепочке."""
        self.start()
        self._done.wait()
        if self._error is not None:
            raise self._error
        return self._value

    def _prepare(self) -> None:
        try:
            self._value = self.make()
        except Exception as error:
            self._error = error
        finally:
            self._done.set()
