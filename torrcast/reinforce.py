"""Совместимый фасад добора кандидатов."""

import sys

from torrcast.adapters.reinforce_environment import environment
from torrcast.usecases import reinforce as _implementation
from torrcast.usecases.reinforce import *  # noqa: F403

__all__ = _implementation.__all__

_implementation.configure(environment)

sys.modules[__name__] = _implementation
