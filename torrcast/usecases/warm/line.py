"""Одна строка о прогреве для человека: сколько уже на диске и что дальше.

Зовут её журнал показа, статус и всякий рассказ прогрева о себе (:func:`_stall`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.domain.catalogs.phrase import phrase

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _line(state: _State) -> str:
    """Строка о прогреве для журнала и статуса — та самая «прогрето 42 мин из 96»."""
    head = phrase(
        "warm.progress_head",
        warmed=_state._hms(state.warmed),
        duration=_state._hms(state.grid.duration),
    )
    if state.done:
        done = phrase("warm.done_note", head=head)
        if state.after is None:
            return done
        return phrase("warm.next_note", done=done, next=_line(state.after))
    if state.trouble:
        return phrase("warm.trouble_note", head=head, trouble=state.trouble)
    if not state.idle:
        return phrase("warm.warming_on", head=head)
    why = phrase("warm.busy_rival") if state._busy_rival() else phrase("warm.waiting_slot")
    return phrase("warm.warming_why", head=head, why=why)
