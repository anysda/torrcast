"""Типовой фасад адаптера исследования потока."""

from collections.abc import Callable
from dataclasses import asdict as asdict
from typing import Any

from torrcast.adapters.stream_probe import (
    _MEDIA_VERSION as _MEDIA_VERSION,
)
from torrcast.adapters.stream_probe import (
    VIDEO_EXT as VIDEO_EXT,
)
from torrcast.adapters.stream_probe import (
    _keep_media as _keep_media,
)
from torrcast.adapters.stream_probe import (
    _media_cache as _media_cache,
)
from torrcast.adapters.stream_probe import (
    _mtime as _mtime,
)
from torrcast.adapters.stream_probe import (
    _read_media as _read_media,
)
from torrcast.adapters.stream_probe import (
    _run_ffprobe as _run_ffprobe,
)
from torrcast.adapters.stream_probe import (
    _touch as _touch,
)
from torrcast.adapters.stream_probe import (
    _track as _track,
)
from torrcast.adapters.stream_probe import (
    _trim as _trim,
)
from torrcast.adapters.stream_probe import (
    _video_bps as _video_bps,
)
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError as NotFoundError
from torrcast.domain.swarm_error import SwarmError as SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.stream_core import ContactWait, TorrServer

class Supply:
    server: TorrServer
    torrent_hash: str
    magnet: str
    lost: str
    restored: bool
    restored_at: float
    def __init__(self, server: TorrServer, torrent_hash: str = ..., magnet: str = ...) -> None: ...
    def check(self) -> str: ...

def probe(url: str, timeout: float = ..., alive: Any = ...) -> Media: ...
def pick_video_file(files: list[TorrFile]) -> TorrFile: ...
def segment_name(slot: int) -> str: ...
def segment_slot(name: str) -> int: ...
def shelf_weight(directory: Any) -> tuple[int, int]: ...
def swarm_pulse(
    source_url: str, grace: float, wait: ContactWait | None = ...
) -> Callable[[], bool]: ...
