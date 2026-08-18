"""Упаковка потока в HLS: сетка сегментов, карта опорных кадров, прогрев и команда ffmpeg.

Собирает разъехавшиеся по файлам единицы под прежним именем: отсюда их берёт всё,
что звало упаковщика этим путём.
"""

from __future__ import annotations

import bisect
import contextlib
import hashlib
import json
import math
import os
import subprocess
import tempfile
import threading
import time
import urllib.request
from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING, Any, NamedTuple

from torrcast.adapters.stream_pack._keys_shelf import _keys_cache, _read_keys
from torrcast.adapters.stream_pack._pilot_start import _pilot_start
from torrcast.adapters.stream_pack._weigher import _weigher
from torrcast.adapters.stream_pack.container_of import container_of
from torrcast.adapters.stream_pack.ffmpeg_pack_command import ffmpeg_pack_command
from torrcast.adapters.stream_pack.film_keys import (
    _fetching,
    _hold_keys_lock,
    _keys_draft,
    film_keys,
)
from torrcast.adapters.stream_pack.forget_playing import forget_playing
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.grid_for import _extra_mbit, grid_for
from torrcast.adapters.stream_pack.head_open import head_open
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.adapters.stream_pack.mark_playing import mark_playing
from torrcast.adapters.stream_pack.pack_origin import _reorder_slack, _seconds, pack_origin
from torrcast.adapters.stream_pack.pack_start import pack_start
from torrcast.adapters.stream_pack.parse_manifest import parse_manifest
from torrcast.adapters.stream_pack.playing_flag import playing_flag
from torrcast.adapters.stream_pack.pull_head import pull_head
from torrcast.adapters.stream_pack.warm_at import warm_at
from torrcast.adapters.stream_pack.warm_file import warm_file
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.hls_settings import HLS_SEGMENT_SECONDS, MAX_SEGMENT_BYTES
from torrcast.domain.hls_wait import PILOT_TIMEOUT
from torrcast.domain.infra_error import InfraError
from torrcast.domain.warm_open import HEAD_WARM

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
