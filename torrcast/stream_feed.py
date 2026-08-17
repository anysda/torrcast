"""Совместимый фасад сценария подачи потока."""

# ruff: noqa: F403, F405
import sys

from torrcast.usecases import feed_pack as _implementation
from torrcast.usecases.feed_pack import *

__all__ = [
    "CAUTIOUS",
    "PACK_PENDING_BYTES",
    "TYPE_CHECKING",
    "_TIMEOUT",
    "Any",
    "Feed",
    "InfraError",
    "Packer",
    "Path",
    "_names",
    "_paths",
    "contextlib",
    "dataclass",
    "field",
    "merge_tracks",
    "os",
    "replace",
    "shutil",
    "subprocess",
    "tempfile",
    "threading",
    "time",
    "timeline_shift",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
