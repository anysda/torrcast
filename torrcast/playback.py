"""Совместимый фасад сценария показа.

Прежние имена показа - те, что сам сценарий больше не разрешает у себя: медиатракт,
приёмник и часы приходят ему из композиционного корня, а плоскому namespace прежнего
монолита они по-прежнему нужны под старыми именами. Держит их здесь фасад, которому
называть модули вне слоёв не запрещено.
"""

# ruff: noqa: F403, F405
import os as os
import sys
import time as time
from dataclasses import dataclass as dataclass
from typing import TYPE_CHECKING as TYPE_CHECKING

from torrcast import trace as trace
from torrcast.adapters.filesystem.stopwatch import mark as mark
from torrcast.adapters.system_clock import CLOCK as CLOCK
from torrcast.cast import ChromecastReceiver as ChromecastReceiver
from torrcast.cast import make_receiver as make_receiver
from torrcast.console import ask_line as ask_line
from torrcast.profile import detect as detect_profile
from torrcast.recode import Encode as Encode
from torrcast.recode import Recoder as Recoder
from torrcast.recode import whole_encode as whole_encode
from torrcast.state import State as State
from torrcast.stream import Grid as Grid
from torrcast.stream import HlsServer as HlsServer
from torrcast.stream import Supply as Supply
from torrcast.stream import TorrServer as TorrServer
from torrcast.stream import forget_playing as forget_playing
from torrcast.stream import hls_base as hls_base
from torrcast.stream import mark_playing as mark_playing
from torrcast.stream import pick_video_file as pick_video_file
from torrcast.stream import playing_flag as playing_flag
from torrcast.stream import probe as probe
from torrcast.stream import start_play_unit as start_play_unit
from torrcast.stream import stop_play_unit as stop_play_unit
from torrcast.stream import unit_active as unit_active
from torrcast.stream import unit_why as unit_why
from torrcast.stream import warm_file as warm_file
from torrcast.usecases import playback as _implementation
from torrcast.usecases.playback import *

__all__ = [
    "CAUTIOUS",
    "CLOCK",
    "ENDING_RATIO",
    "EXIT_OK",
    "REVIVE_DROP",
    "REVIVE_LIMIT",
    "REVIVE_LIVED",
    "REVIVE_PAUSE",
    "REVIVE_TRIES",
    "START_BUDGET",
    "TYPE_CHECKING",
    "VIDEO_EXT",
    "Any",
    "Callable",
    "ChromecastReceiver",
    "Clock",
    "Config",
    "Encode",
    "Entry",
    "Feed",
    "Grid",
    "HlsServer",
    "InfraError",
    "NoReturn",
    "NotFoundError",
    "Path",
    "Profile",
    "Progress",
    "Receiver",
    "Recoder",
    "Release",
    "StartRefusedError",
    "State",
    "Supply",
    "TorrcastError",
    "TorrFile",
    "TorrServer",
    "Vault",
    "Warmer",
    "_Revival",
    "_asked",
    "_await_playing",
    "_blame_the_end",
    "_blamed",
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
    "_resume",
    "_warmer",
    "ask_line",
    "codec_name",
    "contextlib",
    "dataclass",
    "detect_profile",
    "forget_playing",
    "hls_base",
    "make_receiver",
    "mark_playing",
    "os",
    "pick_video_file",
    "playing_flag",
    "probe",
    "recode_note",
    "recodes_whole",
    "start_play_unit",
    "time",
    "trace",
    "warm_file",
    "warm_key",
    "warm_root",
    "whole_encode",
    "why",
]

_implementation.__all__ = __all__
sys.modules[__name__] = _implementation
