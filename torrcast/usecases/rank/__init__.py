"""Часть CLI; публичный фасад — :mod:`torrcast.cli`.

Реэкспорт правил ранжирования: ворота отбора, порядок меню, счёт отсева и строки про
звук. Ни строчки логики - каждая единица живёт в своём файле пакета.
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, TypeAlias

from torrcast.domain.audio_track import AudioTrack
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.episode import Episode
from torrcast.domain.infra_error import InfraError
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.rank_settings import (
    ALIVE_SEEDERS,
    DISC_RE,
    EXTRAS_MBIT,
    FULL_HD_LIVENESS,
    FULL_HEIGHT,
    GATE_LIVENESS,
    HD_HEIGHT,
    HONEST_RATIO,
    PEER_GRACE,
    SD_BITRATE,
    SEASON_EPISODES,
    SOUND_LIVENESS,
    STEP_GRACE,
    TABLE_LIMIT,
    VOICE_MENU,
)
from torrcast.domain.recode_settings import RECODE_HEIGHT
from torrcast.domain.release import Release
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.console import Console
from torrcast.usecases.choice import warned
from torrcast.usecases.rank._cut import _cut
from torrcast.usecases.rank._gb import _gb
from torrcast.usecases.rank._hms import _hms
from torrcast.usecases.rank.ask import ask
from torrcast.usecases.rank.bitrate_of import bitrate_of
from torrcast.usecases.rank.configure import configure
from torrcast.usecases.rank.default_unnamed import default_unnamed
from torrcast.usecases.rank.drop_reason import drop_reason
from torrcast.usecases.rank.drop_reasons import (
    _CODEC,
    _DISC,
    _EXTRAS,
    _HEAVY,
    _HEVC,
    _NO_EPISODE,
    _PINNED,
    _QUIET,
    _SMALL,
    _SOURCE,
    OFF_SEASON,
)
from torrcast.usecases.rank.gate_open import gate_open
from torrcast.usecases.rank.heard import heard
from torrcast.usecases.rank.hevc_hope import hevc_hope
from torrcast.usecases.rank.honest_shot import honest_shot
from torrcast.usecases.rank.is_candidate import is_candidate
from torrcast.usecases.rank.is_dated import is_dated
from torrcast.usecases.rank.is_dead import is_dead
from torrcast.usecases.rank.is_disc import _DISC_RE, is_disc
from torrcast.usecases.rank.is_extra import is_extra
from torrcast.usecases.rank.is_full_hd import is_full_hd
from torrcast.usecases.rank.last_hope import last_hope
from torrcast.usecases.rank.misses_episode import misses_episode
from torrcast.usecases.rank.needs_whole_recode import needs_whole_recode
from torrcast.usecases.rank.over_ceiling import over_ceiling
from torrcast.usecases.rank.pack_mbit import pack_mbit
from torrcast.usecases.rank.peer_grace import peer_grace
from torrcast.usecases.rank.pick_voice import _ask_voice, _voice_number, pick_voice
from torrcast.usecases.rank.promises_more import promises_more
from torrcast.usecases.rank.quality_text import quality_text
from torrcast.usecases.rank.queue_drops import queue_drops
from torrcast.usecases.rank.rank_releases import rank_releases
from torrcast.usecases.rank.render_table import _pad, render_table
from torrcast.usecases.rank.sound_note import (
    _AUDIO_FILE_EXT,
    _RU_FILE_RE,
    _russian_audio_file,
    sound_note,
)
from torrcast.usecases.rank.sound_step import sound_step
from torrcast.usecases.rank.spoken import _SPOKEN, spoken
from torrcast.usecases.rank.stepdown_note import STEP_RATIO, stepdown_note
from torrcast.usecases.rank.understated import understated
from torrcast.usecases.rank.voice_note import voice_note
from torrcast.usecases.rank.voice_unproven import voice_unproven
from torrcast.usecases.rank.voices_table import voices_table

__all__ = [
    "ALIVE_SEEDERS",
    "DISC_RE",
    "EXTRAS_MBIT",
    "FULL_HD_LIVENESS",
    "FULL_HEIGHT",
    "GATE_LIVENESS",
    "HD_HEIGHT",
    "HONEST_RATIO",
    "OFF_SEASON",
    "PEER_GRACE",
    "RECODE_HEIGHT",
    "SD_BITRATE",
    "SEASON_EPISODES",
    "SOUND_LIVENESS",
    "STEP_GRACE",
    "STEP_RATIO",
    "TABLE_LIMIT",
    "TYPE_CHECKING",
    "VOICE_MENU",
    "_AUDIO_FILE_EXT",
    "_CODEC",
    "_DISC",
    "_DISC_RE",
    "_EXTRAS",
    "_HEAVY",
    "_HEVC",
    "_NO_EPISODE",
    "_PINNED",
    "_QUIET",
    "_RU_FILE_RE",
    "_SMALL",
    "_SOURCE",
    "_SPOKEN",
    "Any",
    "AudioTrack",
    "Console",
    "Episode",
    "Final",
    "InfraError",
    "Media",
    "NotFoundError",
    "Path",
    "Release",
    "Sequence",
    "TorrFile",
    "TypeAlias",
    "_ask_voice",
    "_cut",
    "_gb",
    "_hms",
    "_pad",
    "_russian_audio_file",
    "_voice_number",
    "annotations",
    "ask",
    "bitrate_mbit",
    "bitrate_of",
    "configure",
    "default_unnamed",
    "drop_reason",
    "gate_open",
    "heard",
    "hevc_hope",
    "honest_shot",
    "is_candidate",
    "is_dated",
    "is_dead",
    "is_disc",
    "is_extra",
    "is_full_hd",
    "last_hope",
    "misses_episode",
    "needs_whole_recode",
    "over_ceiling",
    "pack_mbit",
    "peer_grace",
    "pick_voice",
    "promises_more",
    "quality_text",
    "queue_drops",
    "rank_releases",
    "re",
    "render_table",
    "sound_note",
    "sound_step",
    "spoken",
    "stepdown_note",
    "understated",
    "voice_note",
    "voice_unproven",
    "voices_table",
    "warned",
]
