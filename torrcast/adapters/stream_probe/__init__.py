"""Часть медиатракта; публичный фасад - :mod:`torrcast.stream`."""

from __future__ import annotations

import contextlib
import hashlib
import json
import os
import subprocess
import threading
import time
import urllib.request as urllib
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from torrcast.adapters.ffprobe.parse_media import parse_media
from torrcast.adapters.stream_probe.media_fields import _track, _video_bps
from torrcast.adapters.stream_probe.media_shelf import (
    _MEDIA_VERSION,
    _keep_media,
    _media_cache,
    _read_media,
)
from torrcast.adapters.stream_probe.opt_str import _opt_str
from torrcast.adapters.stream_probe.pick_video_file import pick_video_file
from torrcast.adapters.stream_probe.probe import probe
from torrcast.adapters.stream_probe.run_ffprobe import _run_ffprobe
from torrcast.adapters.stream_probe.segment_name import segment_name
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.adapters.stream_probe.shelf import _mtime, _touch, _trim
from torrcast.adapters.stream_probe.shelf_weight import shelf_weight
from torrcast.adapters.stream_probe.supply import Supply
from torrcast.adapters.stream_probe.swarm_pulse import swarm_pulse
from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.hls_settings import _SEGMENT_RE
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.probe_settings import META_GRACE
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.warm_open import HEAD_WARM, PROBE_KEPT, WARM_TIMEOUT

__all__ = [
    "HEAD_WARM",
    "META_GRACE",
    "PROBE_KEPT",
    "TYPE_CHECKING",
    "VIDEO_EXT",
    "WARM_TIMEOUT",
    "_MEDIA_VERSION",
    "_SEGMENT_RE",
    "Any",
    "AudioTrack",
    "Final",
    "InfraError",
    "Media",
    "NotFoundError",
    "Path",
    "Supply",
    "SwarmError",
    "_keep_media",
    "_media_cache",
    "_mtime",
    "_opt_str",
    "_read_media",
    "_run_ffprobe",
    "_touch",
    "_track",
    "_trim",
    "_video_bps",
    "asdict",
    "contextlib",
    "dataclass",
    "hashlib",
    "json",
    "os",
    "parse_media",
    "pick_video_file",
    "probe",
    "segment_name",
    "segment_slot",
    "shelf_weight",
    "subprocess",
    "swarm_pulse",
    "threading",
    "time",
    "urllib",
]
