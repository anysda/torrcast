"""Совместимый фасад файлового конфига и состояния просмотра."""

import sys
from importlib import import_module

from torrcast.adapters.filesystem.state import (
    Config,
    Entry,
    State,
    _write_atomic,
    config_keys,
    config_path,
    load_config,
    save_config,
    state_path,
)
from torrcast.domain.entry import ENDING_RATIO

__all__ = [
    "ENDING_RATIO",
    "Config",
    "Entry",
    "State",
    "_write_atomic",
    "config_keys",
    "config_path",
    "load_config",
    "save_config",
    "state_path",
]

_implementation = import_module("torrcast.adapters.filesystem.state")
sys.modules[__name__] = _implementation
