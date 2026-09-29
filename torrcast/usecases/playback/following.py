"""Чем прогреву заняться, когда серия ляжет на диск целиком.

Кладёт эту ручку показу юнит (:func:`torrcast.usecases.worker._cmd_worker`). Показ заводит
сборку на первом кадре (:meth:`Following.start`), а забирает её цепочка прогрева
(:func:`torrcast.usecases.warm.chain._ask_follow`) и после сбоя спрашивает снова.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from torrcast.usecases.warm.warmer import Warmer

#: Как часто подготовка следующей серии проверяет, отпустил ли её живой показ, секунд.
HOLD_PAUSE = 0.5


class Following(Protocol):
    """Прогрев СЛЕДУЮЩЕЙ серии, собранный заранее: ``None`` - греть больше нечего."""

    def start(self, hold: Callable[[], bool]) -> None:
        """Начать сборку в фоне; пока ``hold()`` истинно, она ждёт и раздачу не трогает."""

    def __call__(self) -> Warmer | None:
        """Отдать прогрев следующей серии; ``None`` - фильм или последняя серия."""


def _free() -> bool:
    return False


def _holding(warmer: Warmer | None) -> Callable[[], bool]:
    """Держать сборку тем же правилом, каким замирает прогрев текущей серии.

    Живому окну показа нужен запас (:meth:`Warmer._must_yield`) - сборка ждёт, как ждёт
    и сам прогрев в цепочке (:func:`torrcast.usecases.warm.chain._ask_follow`). Показ
    снят или прогрев выключен - держать нечем: паспорт и карта опорных кадров лягут в кэш
    и понадобятся автопереходу.
    """
    if warmer is None:
        return _free
    return lambda: not warmer.stopped and warmer._must_yield()


@dataclass(slots=True)
class _PreparedFollowing:
    """Собрать следующий прогрев после первого кадра, не задерживая ни старт, ни стык серий.

    Сборка - это вопросы к раздаче и к процессору (паспорт файла, карта опорных кадров,
    :func:`torrcast.usecases.playback._next_warmer._next_warmer`), поэтому она ждёт, пока
    живому окну показа нужен запас (``hold``), - так же, как ждёт прогрев. Сбой не
    запоминается: моргнула сеть на первом кадре - следующий вопрос цепочки соберёт заново,
    иначе следующая серия не прогрелась бы никогда.
    """

    make: Callable[[], Warmer | None]
    pause: float = HOLD_PAUSE
    _hold: Callable[[], bool] = _free
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _done: threading.Event | None = None
    _value: Warmer | None = None
    _error: Exception | None = None

    def start(self, hold: Callable[[], bool] = _free) -> None:
        """Начать подготовку один раз; повторный первый кадр второй нити не создаёт."""
        with self._lock:
            self._hold = hold
            if self._done is not None:
                return
            done = self._done = threading.Event()
        threading.Thread(
            target=self._prepare, args=(done,), daemon=True, name="torrcast-follow"
        ).start()

    def __call__(self) -> Warmer | None:
        """Отдать подготовленный прогрев; сбой отдаётся цепочке и сборку не запирает."""
        self.start(self._hold)
        with self._lock:
            done = self._done
        if done is not None:
            done.wait()
        with self._lock:
            error, self._error = self._error, None
            if error is not None:
                self._done = None  # следующий вопрос цепочки соберёт заново
                raise error
            return self._value

    def _prepare(self, done: threading.Event) -> None:
        try:
            while self._hold():
                done.wait(self.pause)  # ``done`` до конца сборки не выставлен - это пауза
            self._value = self.make()
        except Exception as error:
            self._error = error
        finally:
            done.set()
