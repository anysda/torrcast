"""Совместимый фасад прогрева показа."""

# ruff: noqa: I001

import sys

from torrcast.usecases import warm as _implementation
from torrcast.usecases.warm import *  # noqa: F403
from torrcast.usecases.warm import (
    FREE_FLOOR as FREE_FLOOR,
    GUARD_HIGH as GUARD_HIGH,
    GUARD_LOW as GUARD_LOW,
    HEAD_BYTES as HEAD_BYTES,
    META as META,
    RUN_DIR as RUN_DIR,
    SKEW_MAX as SKEW_MAX,
    SKEW_TRIES as SKEW_TRIES,
    STARVE_GRACE as STARVE_GRACE,
    WARM_BUDGET as WARM_BUDGET,
)

__all__ = _implementation.__all__

sys.modules[__name__] = _implementation
