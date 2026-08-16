"""Совместимый фасад выбора показа."""

import sys

from torrcast.usecases import choice as _implementation
from torrcast.usecases.choice import *  # noqa: F403

__all__ = _implementation.__all__

sys.modules[__name__] = _implementation
