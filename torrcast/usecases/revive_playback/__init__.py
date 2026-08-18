"""Реэкспорт сценария оживления показа: лестница подъёма и держатель показа.

Ни строчки логики - каждая часть живёт в своём файле пакета. Прежние имена собраны
здесь потому, что плоский namespace прежнего монолита (:mod:`torrcast.cli`) спрашивает
их у одного модуля.
"""

from __future__ import annotations

import os
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from torrcast.domain.debug_handles import TRACE_ENV
from torrcast.domain.entry import ENDING_RATIO
from torrcast.domain.infra_error import InfraError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.revive_settings import (
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
)
from torrcast.domain.start_settings import PAUSE_LIMIT, PAUSE_SECONDS, SAY_SECONDS
from torrcast.ports.clock import Clock
from torrcast.ports.journal import journal
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.choice import _ctl, _Revivable
from torrcast.usecases.feed_pack import Feed
from torrcast.usecases.rank import _hms
from torrcast.usecases.revive_playback._blame import _may, _why
from torrcast.usecases.revive_playback._endure import _endure
from torrcast.usecases.revive_playback._hold import _hold
from torrcast.usecases.revive_playback._resurrect import _resurrect
from torrcast.usecases.revive_playback._revival import _Revival
from torrcast.usecases.revive_playback._revival_state import _RevivalState
from torrcast.usecases.revive_playback._revive_state import (
    TAIL_LIMIT,
    _configure_revive_playback,
)
from torrcast.usecases.revive_playback._screen import (
    _first_frame,
    _note_transitions,
    _note_watch,
    _report,
    _trace_line,
)
from torrcast.usecases.revive_playback._screen_state import _Screen
from torrcast.usecases.source_blame import _asked, _blamed
from torrcast.usecases.warm import Warmer
from torrcast.usecases.watch import Watch

__all__ = [
    "CAUTIOUS",
    "ENDING_RATIO",
    "PAUSE_LIMIT",
    "PAUSE_SECONDS",
    "REVIVE_DROP",
    "REVIVE_LIMIT",
    "REVIVE_LIVED",
    "REVIVE_PAUSE",
    "REVIVE_TRIES",
    "SAY_SECONDS",
    "TAIL_LIMIT",
    "TRACE_ENV",
    "Callable",
    "Clock",
    "Feed",
    "InfraError",
    "Path",
    "Profile",
    "Receiver",
    "StreamSource",
    "Warmer",
    "Watch",
    "_Revivable",
    "_Revival",
    "_RevivalState",
    "_Screen",
    "_asked",
    "_blamed",
    "_configure_revive_playback",
    "_ctl",
    "_endure",
    "_first_frame",
    "_hms",
    "_hold",
    "_may",
    "_note_transitions",
    "_note_watch",
    "_report",
    "_resurrect",
    "_trace_line",
    "_why",
    "annotations",
    "dataclass",
    "field",
    "journal",
    "os",
    "time",
]
