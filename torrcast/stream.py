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
from torrcast.stream_core import AUDIO_BITRATE as AUDIO_BITRATE
from torrcast.stream_core import AUDIO_CHANNELS as AUDIO_CHANNELS
from torrcast.stream_core import AUDIO_CODEC as AUDIO_CODEC
from torrcast.stream_core import AUDIO_MBIT as AUDIO_MBIT
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
from torrcast.stream_core import TS_OVERHEAD as TS_OVERHEAD
from torrcast.stream_core import VOICE_KINDS as VOICE_KINDS
from torrcast.stream_core import WARM_TIMEOUT as WARM_TIMEOUT
from torrcast.stream_core import AudioTrack as AudioTrack
from torrcast.stream_core import ContactWait as ContactWait
from torrcast.stream_core import Media as Media
from torrcast.stream_core import ServerDownError as ServerDownError
from torrcast.stream_core import Studio as Studio
from torrcast.stream_core import TorrFile as TorrFile
from torrcast.stream_core import TorrServer as TorrServer
from torrcast.stream_core import Warmup as Warmup
from torrcast.stream_core import bitrate_mbit as bitrate_mbit
from torrcast.stream_core import codec_name as codec_name
from torrcast.stream_core import color_depth as color_depth
from torrcast.stream_core import recode_note as recode_note
from torrcast.stream_core import recodes_whole as recodes_whole
from torrcast.stream_core import studio_of as studio_of
from torrcast.stream_core import swarm_alive as swarm_alive
from torrcast.stream_core import voice_order as voice_order
from torrcast.stream_feed import Feed as Feed
from torrcast.stream_feed import Packer as Packer
from torrcast.stream_feed import merge_tracks as merge_tracks
from torrcast.stream_feed import timeline_shift as timeline_shift
from torrcast.stream_pack import FilmKeys as FilmKeys
from torrcast.stream_pack import Grid as Grid
from torrcast.stream_pack import container_of as container_of
from torrcast.stream_pack import ffmpeg_pack_command as ffmpeg_pack_command
from torrcast.stream_pack import film_keys as film_keys
from torrcast.stream_pack import forget_playing as forget_playing
from torrcast.stream_pack import grid_for as grid_for
from torrcast.stream_pack import head_open as head_open
from torrcast.stream_pack import hls_dir as hls_dir
from torrcast.stream_pack import mapped_start as mapped_start
from torrcast.stream_pack import mark_playing as mark_playing
from torrcast.stream_pack import pack_start as pack_start
from torrcast.stream_pack import parse_manifest as parse_manifest
from torrcast.stream_pack import playing_flag as playing_flag
from torrcast.stream_pack import pull_head as pull_head
from torrcast.stream_pack import warm_at as warm_at
from torrcast.stream_pack import warm_file as warm_file
from torrcast.stream_probe import Supply as Supply
from torrcast.stream_probe import pick_video_file as pick_video_file
from torrcast.stream_probe import probe as probe
from torrcast.stream_probe import segment_name as segment_name
from torrcast.stream_probe import segment_slot as segment_slot
from torrcast.stream_probe import shelf_weight as shelf_weight
from torrcast.stream_probe import swarm_pulse as swarm_pulse
from torrcast.stream_serve import TRACE as TRACE
from torrcast.stream_serve import HlsServer as HlsServer
from torrcast.stream_serve import hls_base as hls_base
from torrcast.stream_serve import our_address as our_address
from torrcast.stream_serve import start_play_unit as start_play_unit
from torrcast.stream_serve import stop_play_unit as stop_play_unit
from torrcast.stream_serve import unit_active as unit_active
from torrcast.stream_serve import unit_key as unit_key
from torrcast.stream_serve import unit_why as unit_why

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
