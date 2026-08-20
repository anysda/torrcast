"""Сколько диска занято прогретым. Спрашивает проба кэша раздачи (``cast doctor``)."""

from __future__ import annotations

import torrcast.usecases.doctor_environment as _state


def warm_used() -> int:
    """Вес прогретого меряет адаптер среды: где оно лежит, знает он же."""
    return _state.environment.warm_used()
