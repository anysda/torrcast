"""Одна строка о прогреве для человека: сколько уже на диске и что дальше.

Зовут её журнал показа, статус и всякий рассказ прогрева о себе (:func:`_stall`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _line(state: _State) -> str:
    """Строка о прогреве для журнала и статуса — та самая «прогрето 42 мин из 96»."""
    head = f"прогрето {_state._hms(state.warmed)} из {_state._hms(state.grid.duration)}"
    if state.done:
        done = f"{head} - фильм целиком на диске, интернет больше не нужен"
        return done if state.after is None else f"{done}; следующая: {_line(state.after)}"
    if state.trouble:
        return f"{head} - прогрев встал: {state.trouble}"
    if not state.idle:
        return f"{head} - грею дальше"
    why = "уступил перекоду" if state._busy_rival() else "жду запаса показа"
    return f"{head} - грею дальше ({why})"
