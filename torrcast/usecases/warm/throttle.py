"""Уступка живому показу: замереть под просевшим запасом и ожить, когда отпустило.

Зовёт заход прогрева (:func:`_run`) на каждом обороте своего цикла.
"""

from __future__ import annotations

import contextlib
import signal
from typing import TYPE_CHECKING, Protocol

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.settings import GUARD_HIGH, GUARD_LOW, STARVE_GRACE

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


class _Signalled(Protocol):
    """Процесс прогона в том объёме, в каком его знает уступка: ему шлют сигнал."""

    def send_signal(self, number: int) -> None: ...


class _Frozen(Protocol):
    """Прогон, который уступка замораживает и оживляет: нужен ровно его процесс."""

    @property
    def proc(self) -> _Signalled: ...


def _throttle(state: _State, packer: _Frozen) -> None:
    """Показ (или его перекод) просит процессор — прогрев замирает; отпустило — оживает.

    Именно ``SIGSTOP``, а не «снять и начать заново»: снятый прогон обошёлся бы
    показу дырой в звуке на стыке (заголовок модуля), а замерший продолжает с того
    же кадра. Живой упаковке это не грозит ничем: замирает читатель диска, а не тот
    ffmpeg, чьи куски забирает приёмник.
    """
    if state._must_yield():
        if not state.idle:
            state.idle = True
            state.healthy_since = 0.0
            with contextlib.suppress(OSError, ProcessLookupError):
                packer.proc.send_signal(signal.SIGSTOP)
            _state._environment.mark(
                "прогрев замер", запас=round(state.slack), перекод=state._busy_rival()
            )
        return
    if state.idle and _may_resume(state):
        _resume(state, packer)


def _may_resume(state: _State) -> bool:
    """Пора ли оживлять замерший прогрев. Зовётся, когда уступать уже некому.

    Три повода, и все безопасны для показа. Первый - запаса не мерили вовсе
    (``mock``, приёмник молчит): гадать за показ нельзя, а держать прогрев вечно
    замершим из-за отработавшего перекода - тем более. Второй - запас перевалил
    :data:`GUARD_HIGH`: показ с большим отрывом от края, места хватает обоим. Третий -
    запас держится над :data:`GUARD_LOW` дольше :data:`STARVE_GRACE`: это тесный, но
    здоровый показ (идёт вплотную за упаковкой, до :data:`GUARD_HIGH` не дотягивает
    никогда), и без короткого захода прогрев голодал бы вечно.
    """
    if state.slack <= 0:
        return True
    if state.slack > GUARD_HIGH:
        return True
    if state.slack < GUARD_LOW:
        state.healthy_since = 0.0
        return False
    now = _state._environment.monotonic()
    if state.healthy_since == 0.0:
        state.healthy_since = now
        return False
    return now - state.healthy_since >= STARVE_GRACE


def _resume(state: _State, packer: _Frozen) -> None:
    """Снять паузу с замершего прогона; не замирал - ничего не делать."""
    if not state.idle:
        return
    state.idle = False
    state.healthy_since = 0.0
    with contextlib.suppress(OSError, ProcessLookupError):
        packer.proc.send_signal(signal.SIGCONT)
