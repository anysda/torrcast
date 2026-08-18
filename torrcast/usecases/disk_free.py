"""Сколько места на разделе. Спрашивает проба кэша раздачи (``cast doctor``)."""

from __future__ import annotations

import torrcast.usecases.doctor_environment as _state


def disk_free(path: str) -> int:
    """Место на разделе меряет адаптер среды."""
    return _state.environment.disk_free(path)
