"""Совместимый фасад команды показа."""

# ruff: noqa: F403, F405
import sys

from torrcast import trace as trace
from torrcast.usecases import cast_command as _implementation
from torrcast.usecases.cast_command import *

__all__ = [
    "EXIT_OK",
    "TYPE_CHECKING",
    "Entry",
    "Facts",
    "Picture",
    "Progress",
    "Prowlarr",
    "RawResult",
    "State",
    "TorrServer",
    "_cmd_play",
    "_relayout",
    "_season_asked",
    "_titled_number",
    "bitrate_mbit",
    "detect_profile",
    "load_config",
    "mark",
    "merge",
    "season_reread",
    "slugify",
    "split_franchise_index",
    "to_releases",
    "trace",
    "tune_profile",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
