"""Совместимый фасад адаптера упаковки потока."""

# ruff: noqa: F403, F405

import sys

from torrcast.adapters import stream_pack as _implementation
from torrcast.adapters.stream_pack import *

__all__ = [
    "HEAD_WARM",
    "HLS_SEGMENT_SECONDS",
    "MAX_SEGMENT_BYTES",
    "PILOT_TIMEOUT",
    "TYPE_CHECKING",
    "Any",
    "FilmKeys",
    "Grid",
    "InfraError",
    "NamedTuple",
    "Path",
    "_extra_mbit",
    "_fetching",
    "_hold_keys_lock",
    "_keys_cache",
    "_keys_draft",
    "_pilot_start",
    "_read_keys",
    "_reorder_slack",
    "_seconds",
    "_weigher",
    "bisect",
    "container_of",
    "contextlib",
    "dataclass",
    "ffmpeg_pack_command",
    "film_keys",
    "forget_playing",
    "grid_for",
    "hashlib",
    "head_open",
    "hls_dir",
    "json",
    "mapped_start",
    "mark",
    "mark_playing",
    "math",
    "os",
    "pack_origin",
    "pack_start",
    "parse_manifest",
    "playing_flag",
    "pull_head",
    "replace",
    "subprocess",
    "tempfile",
    "threading",
    "time",
    "urllib",
    "warm_at",
    "warm_file",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
