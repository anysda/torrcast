"""Реэкспорт сценария показа: запуск, тракт, прогрев и конец показа.

Ни строчки логики - каждая часть живёт в своём файле пакета. Прежние имена собраны
здесь потому, что плоский namespace прежнего монолита (:mod:`torrcast.cli`) спрашивает
их у одного модуля.
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from typing import Any, NoReturn, Protocol, runtime_checkable

from torrcast.domain._name_data.data_3 import VIDEO_EXT
from torrcast.domain.choice import Choice
from torrcast.domain.codec_name import codec_name
from torrcast.domain.config import Config
from torrcast.domain.entry import ENDING_RATIO, Entry
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.release import Release
from torrcast.domain.revive_settings import (
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
)
from torrcast.domain.start_refused_error import StartRefusedError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.why import why
from torrcast.domain.worker_settings import WORKER_DUR
from torrcast.ports.clock import Clock
from torrcast.ports.journal import journal
from torrcast.ports.prober import Prober
from torrcast.ports.progress import Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.ports.receiver import Receiver
from torrcast.ports.receivers import Receivers
from torrcast.ports.recode.encoding import Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder
from torrcast.ports.show_unit import ShowUnit
from torrcast.ports.show_unit import unit as show_unit
from torrcast.ports.state_store import store
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.feed_pack import Feed
from torrcast.usecases.playback._cuttable import _Cuttable
from torrcast.usecases.playback._encode_all import _encode_all
from torrcast.usecases.playback._file_picker import _default_file, _file_picker
from torrcast.usecases.playback._launch import (
    _await_playing,
    _launch,
    _refuse_hopeless,
    _resume,
)
from torrcast.usecases.playback._layout import _layout
from torrcast.usecases.playback._numbered import _Numbered
from torrcast.usecases.playback._play import _play
from torrcast.usecases.playback._recoder import _recoder
from torrcast.usecases.playback._show_end import (
    _blame_the_end,
    _close_show,
    _handover,
    _report_end,
    _say_whole,
)
from torrcast.usecases.playback._show_state import _configure_playback
from torrcast.usecases.playback._tract import _tract
from torrcast.usecases.playback._warmer import _next_warmer, _warmer
from torrcast.usecases.playback.following import Following
from torrcast.usecases.playback.heavy_profile import HeavyProfile
from torrcast.usecases.playback.heavy_profiles import HeavyProfileOf
from torrcast.usecases.playback.media_grid import MediaGrid
from torrcast.usecases.playback.media_grids import MediaGrids
from torrcast.usecases.playback.spot_encodings import SpotEncodings
from torrcast.usecases.playback.spot_recoders import SpotRecoders
from torrcast.usecases.playback.stream_server import StreamServer
from torrcast.usecases.playback.stream_servers import StreamServers
from torrcast.usecases.playback.whole_encodings import WholeEncodings
from torrcast.usecases.revive_playback import _hold, _Revival
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._plan import _Plan
from torrcast.usecases.source_blame import _asked, _blamed
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.warm import Vault, Warmer, warm_key, warm_root
from torrcast.usecases.watch import Watch

__all__ = [
    "AUDIO_MBIT",
    "CAUTIOUS",
    "ENDING_RATIO",
    "EXIT_OK",
    "REVIVE_DROP",
    "REVIVE_LIMIT",
    "REVIVE_LIVED",
    "REVIVE_PAUSE",
    "REVIVE_TRIES",
    "START_BUDGET",
    "TS_OVERHEAD",
    "VIDEO_EXT",
    "WORKER_DUR",
    "Any",
    "Callable",
    "Choice",
    "Clock",
    "Config",
    "Encoding",
    "Entry",
    "Feed",
    "FilmKeys",
    "Following",
    "HeavyProfile",
    "HeavyProfileOf",
    "InfraError",
    "MediaGrid",
    "MediaGrids",
    "NoReturn",
    "NotFoundError",
    "Path",
    "Prober",
    "Profile",
    "Progress",
    "Protocol",
    "Receiver",
    "Receivers",
    "Release",
    "ShowUnit",
    "SpotEncodings",
    "SpotRecoder",
    "SpotRecoders",
    "StartRefusedError",
    "StreamServer",
    "StreamServers",
    "StreamSource",
    "TorrcastError",
    "TorrFile",
    "Vault",
    "Warmer",
    "Watch",
    "WholeEncodings",
    "_Clock",
    "_Cuttable",
    "_Numbered",
    "_Plan",
    "_Revival",
    "_about",
    "_asked",
    "_await_playing",
    "_blame_the_end",
    "_blamed",
    "_close_show",
    "_configure_playback",
    "_default_file",
    "_encode_all",
    "_file_picker",
    "_handover",
    "_hold",
    "_launch",
    "_layout",
    "_next_warmer",
    "_play",
    "_recoder",
    "_refuse_hopeless",
    "_report_end",
    "_resume",
    "_say_whole",
    "_tract",
    "_warmer",
    "annotations",
    "codec_name",
    "contextlib",
    "journal",
    "progress_bar",
    "recode_note",
    "recodes_whole",
    "runtime_checkable",
    "show_unit",
    "store",
    "warm_key",
    "warm_root",
    "why",
]
