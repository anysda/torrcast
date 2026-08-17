import contextlib as contextlib
import os as os
import time as time
from collections.abc import Callable as Callable
from dataclasses import dataclass as dataclass
from pathlib import Path as Path
from types import ModuleType
from typing import TYPE_CHECKING as TYPE_CHECKING
from typing import Any as Any
from typing import NoReturn as NoReturn

from torrcast import InfraError as InfraError
from torrcast import NotFoundError as NotFoundError
from torrcast import TorrcastError as TorrcastError
from torrcast import trace as trace
from torrcast import why as why
from torrcast.cast import ChromecastReceiver as ChromecastReceiver
from torrcast.cast import Receiver as Receiver
from torrcast.cast import StartRefusedError as StartRefusedError
from torrcast.cast import make_receiver as make_receiver
from torrcast.commands import EXIT_OK as EXIT_OK
from torrcast.commands import REVIVE_DROP as REVIVE_DROP
from torrcast.commands import REVIVE_LIMIT as REVIVE_LIMIT
from torrcast.commands import REVIVE_LIVED as REVIVE_LIVED
from torrcast.commands import REVIVE_PAUSE as REVIVE_PAUSE
from torrcast.commands import REVIVE_TRIES as REVIVE_TRIES
from torrcast.commands import START_BUDGET as START_BUDGET
from torrcast.commands import Args, Watch, _Clock
from torrcast.console import Progress as Progress
from torrcast.console import ask_line as ask_line
from torrcast.parse import VIDEO_EXT as VIDEO_EXT
from torrcast.parse import Release as Release
from torrcast.playback_revival import _hold as _hold
from torrcast.playback_revival import _Revival as _Revival
from torrcast.ports.show_unit import ShowUnit as ShowUnit
from torrcast.profile import CAUTIOUS as CAUTIOUS
from torrcast.profile import Profile as Profile
from torrcast.profile import detect as detect_profile
from torrcast.recode import Encode as Encode
from torrcast.recode import Recoder as Recoder
from torrcast.recode import whole_encode as whole_encode
from torrcast.selection import _Plan
from torrcast.state import ENDING_RATIO as ENDING_RATIO
from torrcast.state import Config as Config
from torrcast.state import Entry as Entry
from torrcast.state import State as State
from torrcast.stream import Feed as Feed
from torrcast.stream import Grid as Grid
from torrcast.stream import HlsServer as HlsServer
from torrcast.stream import Supply as Supply
from torrcast.stream import TorrFile as TorrFile
from torrcast.stream import TorrServer as TorrServer
from torrcast.stream import codec_name as codec_name
from torrcast.stream import forget_playing as forget_playing
from torrcast.stream import hls_base as hls_base
from torrcast.stream import mark_playing as mark_playing
from torrcast.stream import pick_video_file as pick_video_file
from torrcast.stream import playing_flag as playing_flag
from torrcast.stream import probe as probe
from torrcast.stream import recode_note as recode_note
from torrcast.stream import recodes_whole as recodes_whole
from torrcast.stream import start_play_unit as start_play_unit
from torrcast.stream import stop_play_unit as stop_play_unit
from torrcast.stream import unit_active as unit_active
from torrcast.stream import unit_why as unit_why
from torrcast.stream import warm_file as warm_file
from torrcast.timing import CLOCK as CLOCK
from torrcast.timing import Clock as Clock
from torrcast.timing import mark as mark
from torrcast.warm import Vault as Vault
from torrcast.warm import Warmer as Warmer
from torrcast.warm import warm_key as warm_key
from torrcast.warm import warm_root as warm_root

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
    "mark",
    "mark_playing",
    "os",
    "pick_video_file",
    "playing_flag",
    "probe",
    "recode_note",
    "recodes_whole",
    "start_play_unit",
    "stop_play_unit",
    "time",
    "trace",
    "unit_active",
    "unit_why",
    "warm_file",
    "warm_key",
    "warm_root",
    "whole_encode",
    "why",
]

def _default_file(plan: _Plan, release: Release, files: list[TorrFile]) -> TorrFile: ...
def _file_picker(args: Args) -> Callable[[_Plan, Release, list[TorrFile]], TorrFile]: ...
def _resume(config: Config, key: str, entry: Entry, clock: _Clock, dry: bool = False) -> int: ...
def _launch(
    config: Config, key: str, entry: Entry, about: str, clock: _Clock, dry: bool = False
) -> int: ...
def _refuse_hopeless(config: Config, entry: Entry) -> None: ...
def _await_playing(
    config: Config,
    progress: Progress,
    timeout: float = ...,
    clock: Clock = ...,
    unit: ShowUnit | None = ...,
) -> None: ...
def _recoder(
    source: str,
    audio: int,
    grid: Grid,
    spare: Path,
    config: Config,
    video_mbit: float = 0.0,
    profile: Profile = ...,
) -> Recoder | None: ...
def _encode_all(
    config: Config,
    codec: str,
    video_mbit: float = 0.0,
    depth: int = 0,
    profile: Profile = ...,
    frame: int = 0,
    hdr: bool = False,
) -> Encode | None: ...
def _layout(
    config: Config,
    source: str,
    length: float,
    codec: str,
    video_mbit: float,
    say: Any = None,
    depth: int = 0,
    profile: Profile = ...,
    frame: int = 0,
    hdr: bool = False,
) -> tuple[Grid, Encode | None]: ...
def _next_warmer(
    config: Config, torrserver: Any, torrent_hash: str, entry: Entry, profile: Profile = ...
) -> Warmer | None: ...
def _warmer(
    config: Config,
    source: str,
    audio: int,
    grid: Grid,
    start: float,
    title: str,
    whole: Any = None,
    recoder: Any = None,
    follow: Any = None,
    profile: Profile = ...,
) -> Warmer | None: ...
def _play(
    config: Config,
    source: str,
    audio: int,
    about: str,
    clock: _Clock,
    watch: Watch | None = None,
    duration: float = 0.0,
    receiver: Receiver | None = None,
    codec: str = "",
    depth: int = 0,
    follow: Any = None,
    supply: Supply | None = None,
    profile: Profile = ...,
    frame: int = 0,
    hdr: bool = False,
    session_tag: str = "",
) -> int: ...
def _handover(watch: Watch | None) -> bool: ...
def _blame_the_end(supply: Supply | None, shown: bool = True, clock: Clock = ...) -> NoReturn: ...
def _blamed(supply: Supply | None, clock: Clock = ...) -> str: ...
def _asked(supply: Supply | None) -> str: ...

class _PlaybackModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None: ...
