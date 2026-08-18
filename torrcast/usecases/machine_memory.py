"""Сколько памяти у машины. Спрашивает проба кэша раздачи (``cast doctor``)."""

from __future__ import annotations

import torrcast.usecases.doctor_environment as _state


def machine_memory() -> int:
    """Память машины меряет адаптер среды."""
    return _state.environment.machine_memory()
