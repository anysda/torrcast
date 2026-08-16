"""Совместимый фасад выбора показа."""

import os
import shutil
import sys

from torrcast import console, trace
from torrcast.adapters.choice_environment import environment
from torrcast.cast import Receiver
from torrcast.console import Progress
from torrcast.facts import Fact, Facts, Origin, origin, shorten
from torrcast.state import Config
from torrcast.usecases import choice as _implementation
from torrcast.usecases.choice import *  # noqa: F403

_implementation.configure(environment)

# Старый агрегирующий CLI пока импортирует эти имена из фасада. Они не являются
# зависимостями сценария: композиционный корень оставляет их на совместимом модуле.
for _name, _value in {
    "Config": Config,
    "Fact": Fact,
    "Facts": Facts,
    "Origin": Origin,
    "Progress": Progress,
    "Receiver": Receiver,
    "console": console,
    "origin": origin,
    "os": os,
    "shorten": shorten,
    "shutil": shutil,
    "trace": trace,
}.items():
    setattr(_implementation, _name, _value)
    globals()[_name] = _value

__all__ = _implementation.__all__

sys.modules[__name__] = _implementation
