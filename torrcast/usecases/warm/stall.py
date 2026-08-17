"""Прогрев встал и след о том, сколько он успел.

Зовут нитка прогрева (:func:`_work`) и сверка укладки (:func:`_verify`).
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.warm._state as _state
from torrcast.usecases.warm.line import _line

if TYPE_CHECKING:
    from torrcast.usecases.warm.warmer_state import _State


def _stall(state: _State, why: str) -> None:
    """Прогрев дальше не идёт: сказать это вслух, в журнал и в недельный след."""
    state.trouble = why
    state._say(_line(state))
    _state._environment.mark("прогрев встал", причина=why, секунд=round(state.warmed))
    _trace(state, "stall", why)


def _trace(state: _State, event: str, why: str = "") -> None:
    """Доля прогретого в недельный след - полями, а не строкой журнала.

    Строка (:func:`_line`) остаётся человеку в живом показе, а сюда идут те же числа
    врозь: секунды на диске, длина фильма и вес каталога. По ним и через неделю видно,
    сколько успел прогрев, - без разбора текста.
    """
    _state._environment.emit(
        "warmth",
        event,
        secs=state.warmed,
        dur=state.grid.duration,
        size=state.vault.size(),
        why=why,
    )
