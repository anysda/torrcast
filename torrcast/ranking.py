"""Совместимый фасад правил ранжирования."""

import sys

from torrcast.adapters.rank_environment import environment
from torrcast.usecases import rank as _implementation
from torrcast.usecases.rank import *  # noqa: F403
from torrcast.usecases.rank import default_unnamed as default_unnamed

__all__ = _implementation.__all__

_implementation.configure(environment)

sys.modules[__name__] = _implementation
