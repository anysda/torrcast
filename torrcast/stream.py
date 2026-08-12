"""Совместимый фасад медиатракта."""

from __future__ import annotations

import sys
from types import ModuleType
from typing import Any

from torrcast import stream_core as _stream_core
from torrcast import stream_feed as _stream_feed
from torrcast import stream_pack as _stream_pack
from torrcast import stream_probe as _stream_probe
from torrcast import stream_serve as _stream_serve
from torrcast.stream_core import (
    _DEPTH_FMT as _DEPTH_FMT,
)
from torrcast.stream_core import (
    _DEPTH_PROFILE as _DEPTH_PROFILE,
)
from torrcast.stream_core import (
    _FOREIGN_TITLE_RE as _FOREIGN_TITLE_RE,
)
from torrcast.stream_core import (
    _ORIGINAL_RE as _ORIGINAL_RE,
)
from torrcast.stream_core import (
    _PASS_ENV as _PASS_ENV,
)
from torrcast.stream_core import (
    _RU_LANG as _RU_LANG,
)
from torrcast.stream_core import (
    _RU_TITLE_RE as _RU_TITLE_RE,
)
from torrcast.stream_core import (
    _SEEK_LOCK as _SEEK_LOCK,
)
from torrcast.stream_core import (
    _SEEK_OK as _SEEK_OK,
)
from torrcast.stream_core import (
    _SEGMENT_RE as _SEGMENT_RE,
)
from torrcast.stream_core import (
    _SERVICE_RE as _SERVICE_RE,
)
from torrcast.stream_core import (
    _TECH_RE as _TECH_RE,
)
from torrcast.stream_core import (
    _UNIT_TAG as _UNIT_TAG,
)
from torrcast.stream_core import (
    _VAGUE_LANG as _VAGUE_LANG,
)
from torrcast.stream_core import (
    _VOICE_STEPS as _VOICE_STEPS,
)
from torrcast.stream_core import (
    _WORDS_RE as _WORDS_RE,
)
from torrcast.stream_core import AUDIO_BITRATE as AUDIO_BITRATE
from torrcast.stream_core import AUDIO_CHANNELS as AUDIO_CHANNELS
from torrcast.stream_core import AUDIO_CODEC as AUDIO_CODEC
from torrcast.stream_core import AUDIO_MBIT as AUDIO_MBIT
from torrcast.stream_core import (
    COPY as COPY,
)
from torrcast.stream_core import COPY_DEPTH as COPY_DEPTH
from torrcast.stream_core import HEAD_OPEN as HEAD_OPEN
from torrcast.stream_core import HEAD_OPEN_DEFAULT as HEAD_OPEN_DEFAULT
from torrcast.stream_core import HEAD_WARM as HEAD_WARM
from torrcast.stream_core import HLS_SEGMENT_SECONDS as HLS_SEGMENT_SECONDS
from torrcast.stream_core import KEYS_KEPT as KEYS_KEPT
from torrcast.stream_core import KEYS_LOCK as KEYS_LOCK
from torrcast.stream_core import KEYS_WAIT as KEYS_WAIT
from torrcast.stream_core import MAX_SEGMENT_BYTES as MAX_SEGMENT_BYTES
from torrcast.stream_core import META_GRACE as META_GRACE
from torrcast.stream_core import META_STEP as META_STEP
from torrcast.stream_core import META_STEP_GROW as META_STEP_GROW
from torrcast.stream_core import META_STEP_MAX as META_STEP_MAX
from torrcast.stream_core import MIXED_PREFIX as MIXED_PREFIX
from torrcast.stream_core import MPEGTS_MUX_DELAY as MPEGTS_MUX_DELAY
from torrcast.stream_core import MUTE_SECONDS as MUTE_SECONDS
from torrcast.stream_core import PACK_DIR as PACK_DIR
from torrcast.stream_core import PACK_LIST as PACK_LIST
from torrcast.stream_core import PACK_PENDING_BYTES as PACK_PENDING_BYTES
from torrcast.stream_core import PILOT_TIMEOUT as PILOT_TIMEOUT
from torrcast.stream_core import PLAYING_FLAG as PLAYING_FLAG
from torrcast.stream_core import PROBE_KEPT as PROBE_KEPT
from torrcast.stream_core import PROBE_TIMEOUT as PROBE_TIMEOUT
from torrcast.stream_core import RECODE_CODECS as RECODE_CODECS
from torrcast.stream_core import RECODE_DIR as RECODE_DIR
from torrcast.stream_core import RUNTIME_GUESS as RUNTIME_GUESS
from torrcast.stream_core import SEEK_SHIFT as SEEK_SHIFT
from torrcast.stream_core import SHRINK_DIR as SHRINK_DIR
from torrcast.stream_core import SPLIT_SLACK as SPLIT_SLACK
from torrcast.stream_core import STEP_FOREIGN as STEP_FOREIGN
from torrcast.stream_core import STEP_ORIGINAL as STEP_ORIGINAL
from torrcast.stream_core import STEP_RU_PLAIN as STEP_RU_PLAIN
from torrcast.stream_core import STEP_SERVICE as STEP_SERVICE
from torrcast.stream_core import STUDIOS as STUDIOS
from torrcast.stream_core import (
    TIMELINE_ENV as TIMELINE_ENV,
)
from torrcast.stream_core import TS_OVERHEAD as TS_OVERHEAD
from torrcast.stream_core import VOICE_KINDS as VOICE_KINDS
from torrcast.stream_core import WARM_TIMEOUT as WARM_TIMEOUT
from torrcast.stream_core import AudioTrack as AudioTrack
from torrcast.stream_core import ContactWait as ContactWait
from torrcast.stream_core import Media as Media
from torrcast.stream_core import (
    Profile as Profile,
)
from torrcast.stream_core import ServerDownError as ServerDownError
from torrcast.stream_core import Studio as Studio
from torrcast.stream_core import TorrFile as TorrFile
from torrcast.stream_core import TorrServer as TorrServer
from torrcast.stream_core import Warmup as Warmup
from torrcast.stream_core import (
    _file_stats as _file_stats,
)
from torrcast.stream_core import bitrate_mbit as bitrate_mbit
from torrcast.stream_core import codec_name as codec_name
from torrcast.stream_core import color_depth as color_depth
from torrcast.stream_core import (
    quote as quote,
)
from torrcast.stream_core import recode_note as recode_note
from torrcast.stream_core import recodes_whole as recodes_whole
from torrcast.stream_core import studio_of as studio_of
from torrcast.stream_core import swarm_alive as swarm_alive
from torrcast.stream_core import voice_order as voice_order
from torrcast.stream_feed import (
    _TIMEOUT as _TIMEOUT,
)
from torrcast.stream_feed import (
    CAUTIOUS as CAUTIOUS,
)
from torrcast.stream_feed import Feed as Feed
from torrcast.stream_feed import Packer as Packer
from torrcast.stream_feed import (
    _names as _names,
)
from torrcast.stream_feed import (
    _paths as _paths,
)
from torrcast.stream_feed import (
    dataclass as dataclass,
)
from torrcast.stream_feed import (
    field as field,
)
from torrcast.stream_feed import (
    mark as mark,
)
from torrcast.stream_feed import merge_tracks as merge_tracks
from torrcast.stream_feed import (
    replace as replace,
)
from torrcast.stream_feed import (
    shutil as shutil,
)
from torrcast.stream_feed import (
    tempfile as tempfile,
)
from torrcast.stream_feed import timeline_shift as timeline_shift
from torrcast.stream_pack import FilmKeys as FilmKeys
from torrcast.stream_pack import Grid as Grid
from torrcast.stream_pack import (
    NamedTuple as NamedTuple,
)
from torrcast.stream_pack import (
    _extra_mbit as _extra_mbit,
)
from torrcast.stream_pack import (
    _fetching as _fetching,
)
from torrcast.stream_pack import (
    _hold_keys_lock as _hold_keys_lock,
)
from torrcast.stream_pack import (
    _keys_cache as _keys_cache,
)
from torrcast.stream_pack import (
    _keys_draft as _keys_draft,
)
from torrcast.stream_pack import (
    _pilot_start as _pilot_start,
)
from torrcast.stream_pack import (
    _read_keys as _read_keys,
)
from torrcast.stream_pack import (
    _weigher as _weigher,
)
from torrcast.stream_pack import (
    bisect as bisect,
)
from torrcast.stream_pack import container_of as container_of
from torrcast.stream_pack import ffmpeg_pack_command as ffmpeg_pack_command
from torrcast.stream_pack import film_keys as film_keys
from torrcast.stream_pack import forget_playing as forget_playing
from torrcast.stream_pack import grid_for as grid_for
from torrcast.stream_pack import (
    hashlib as hashlib,
)
from torrcast.stream_pack import head_open as head_open
from torrcast.stream_pack import hls_dir as hls_dir
from torrcast.stream_pack import (
    json as json,
)
from torrcast.stream_pack import mapped_start as mapped_start
from torrcast.stream_pack import mark_playing as mark_playing
from torrcast.stream_pack import (
    math as math,
)
from torrcast.stream_pack import pack_start as pack_start
from torrcast.stream_pack import parse_manifest as parse_manifest
from torrcast.stream_pack import playing_flag as playing_flag
from torrcast.stream_pack import pull_head as pull_head
from torrcast.stream_pack import (
    urllib as urllib,
)
from torrcast.stream_pack import warm_at as warm_at
from torrcast.stream_pack import warm_file as warm_file
from torrcast.stream_probe import (
    _MEDIA_VERSION as _MEDIA_VERSION,
)
from torrcast.stream_probe import (
    VIDEO_EXT as VIDEO_EXT,
)
from torrcast.stream_probe import (
    NotFoundError as NotFoundError,
)
from torrcast.stream_probe import Supply as Supply
from torrcast.stream_probe import (
    SwarmError as SwarmError,
)
from torrcast.stream_probe import (
    _keep_media as _keep_media,
)
from torrcast.stream_probe import (
    _media_cache as _media_cache,
)
from torrcast.stream_probe import (
    _mtime as _mtime,
)
from torrcast.stream_probe import (
    _read_media as _read_media,
)
from torrcast.stream_probe import (
    _run_ffprobe as _run_ffprobe,
)
from torrcast.stream_probe import (
    _touch as _touch,
)
from torrcast.stream_probe import (
    _track as _track,
)
from torrcast.stream_probe import (
    _trim as _trim,
)
from torrcast.stream_probe import (
    _video_bps as _video_bps,
)
from torrcast.stream_probe import (
    asdict as asdict,
)
from torrcast.stream_probe import pick_video_file as pick_video_file
from torrcast.stream_probe import probe as probe
from torrcast.stream_probe import segment_name as segment_name
from torrcast.stream_probe import segment_slot as segment_slot
from torrcast.stream_probe import shelf_weight as shelf_weight
from torrcast.stream_probe import swarm_pulse as swarm_pulse
from torrcast.stream_serve import (
    _ASSET_RE as _ASSET_RE,
)
from torrcast.stream_serve import (
    _RANGE_RE as _RANGE_RE,
)
from torrcast.stream_serve import (
    _TYPES as _TYPES,
)
from torrcast.stream_serve import (
    _UNIT_NAME as _UNIT_NAME,
)
from torrcast.stream_serve import TRACE as TRACE
from torrcast.stream_serve import (
    TYPE_CHECKING as TYPE_CHECKING,
)
from torrcast.stream_serve import (
    ClassVar as ClassVar,
)
from torrcast.stream_serve import (
    Final as Final,
)
from torrcast.stream_serve import HlsServer as HlsServer
from torrcast.stream_serve import (
    InfraError as InfraError,
)
from torrcast.stream_serve import (
    Path as Path,
)
from torrcast.stream_serve import (
    _Handler as _Handler,
)
from torrcast.stream_serve import (
    _opt_str as _opt_str,
)
from torrcast.stream_serve import (
    _scope as _scope,
)
from torrcast.stream_serve import (
    _Server as _Server,
)
from torrcast.stream_serve import (
    _systemd as _systemd,
)
from torrcast.stream_serve import (
    contextlib as contextlib,
)
from torrcast.stream_serve import hls_base as hls_base
from torrcast.stream_serve import (
    http as http,
)
from torrcast.stream_serve import (
    os as os,
)
from torrcast.stream_serve import our_address as our_address
from torrcast.stream_serve import (
    re as re,
)
from torrcast.stream_serve import (
    socket as socket,
)
from torrcast.stream_serve import (
    ssl as ssl,
)
from torrcast.stream_serve import start_play_unit as start_play_unit
from torrcast.stream_serve import stop_play_unit as stop_play_unit
from torrcast.stream_serve import (
    subprocess as subprocess,
)
from torrcast.stream_serve import (
    threading as threading,
)
from torrcast.stream_serve import (
    time as time,
)
from torrcast.stream_serve import unit_active as unit_active
from torrcast.stream_serve import unit_key as unit_key
from torrcast.stream_serve import unit_why as unit_why
from torrcast.stream_serve import (
    why as why,
)

_PARTS = (_stream_core, _stream_probe, _stream_pack, _stream_feed, _stream_serve,)
_namespace: dict[str, Any] = {}
for _part in _PARTS:
    _namespace.update(
        (name, value)
        for name, value in vars(_part).items()
        if not name.startswith("__")
    )
globals().update(_namespace)
for _part in _PARTS:
    vars(_part).update(_namespace)

class _StreamModule(ModuleType):
    def __setattr__(self, name: str, value: Any) -> None:
        super().__setattr__(name, value)
        if not name.startswith("__"):
            for part in _PARTS:
                if name in vars(part):
                    setattr(part, name, value)

sys.modules[__name__].__class__ = _StreamModule
__all__ = [name for name in globals() if not name.startswith("_")]
