"""TorrServer, ffprobe и упаковка потока в HLS. Своего CDN-кода нет: раздачу отдаёт
TorrServer (кэш в RAM, на диск не пишем), пакует ffmpeg. Формат для ТВ
зафиксирован: HLS, сегменты MPEG-TS по сетке ~10 с (замер: на сетке 4 с приёмник
разработки встаёт намертво на границе сегмента), один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

from torrcast.adapters.recode import RECODE_DIR
from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.torr_server import (
    META_STEP,
    META_STEP_GROW,
    META_STEP_MAX,
    TorrServer,
    _file_stats,
)
from torrcast.adapters.torrserver.warmup import Warmup
from torrcast.domain.audio_track import (
    _FOREIGN_TITLE_RE,
    _ORIGINAL_RE,
    _RU_LANG,
    _RU_TITLE_RE,
    _SERVICE_RE,
    _TECH_RE,
    _VAGUE_LANG,
    _VOICE_STEPS,
    STEP_FOREIGN,
    STEP_ORIGINAL,
    STEP_RU_PLAIN,
    STEP_SERVICE,
    VOICE_KINDS,
    AudioTrack,
)
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.codec_name import codec_name
from torrcast.domain.color_depth import _DEPTH_FMT, _DEPTH_PROFILE, color_depth
from torrcast.domain.hls_settings import (
    _SEGMENT_RE,
    AUDIO_BITRATE,
    AUDIO_CHANNELS,
    AUDIO_CODEC,
    HLS_SEGMENT_SECONDS,
    MAX_SEGMENT_BYTES,
    MIXED_PREFIX,
    MPEGTS_MUX_DELAY,
    MUTE_SECONDS,
    PACK_DIR,
    PACK_LIST,
    PACK_PENDING_BYTES,
    PACK_SHORT_SECONDS,
    PLAYING_FLAG,
    SHRINK_DIR,
    SPLIT_SLACK,
)
from torrcast.domain.hls_wait import KEYS_WAIT, PILOT_TIMEOUT
from torrcast.domain.media import AUDIO_MBIT, TS_OVERHEAD, Media
from torrcast.domain.probe_settings import (
    _TIMEOUT,
    COPY_DEPTH,
    META_GRACE,
    PROBE_TIMEOUT,
    RECODE_CODECS,
)
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recodes_whole import recodes_whole
from torrcast.domain.runtime_guess import RUNTIME_GUESS
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.studio import STUDIOS, Studio
from torrcast.domain.studio_of import _WORDS_RE, studio_of
from torrcast.domain.swarm_alive import swarm_alive
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.unit_naming import _PASS_ENV, _UNIT_NAME, _UNIT_TAG
from torrcast.domain.voice_order import voice_order
from torrcast.domain.warm_open import (
    HEAD_OPEN,
    HEAD_OPEN_DEFAULT,
    HEAD_WARM,
    KEYS_KEPT,
    KEYS_LOCK,
    PROBE_KEPT,
    SEEK_SHIFT,
    WARM_TIMEOUT,
)

__all__ = [
    "AUDIO_BITRATE",
    "AUDIO_CHANNELS",
    "AUDIO_CODEC",
    "AUDIO_MBIT",
    "CAUTIOUS",
    "COPY",
    "COPY_DEPTH",
    "HEAD_OPEN",
    "HEAD_OPEN_DEFAULT",
    "HEAD_WARM",
    "HLS_SEGMENT_SECONDS",
    "KEYS_KEPT",
    "KEYS_LOCK",
    "KEYS_WAIT",
    "MAX_SEGMENT_BYTES",
    "META_GRACE",
    "META_STEP",
    "META_STEP_GROW",
    "META_STEP_MAX",
    "MIXED_PREFIX",
    "MPEGTS_MUX_DELAY",
    "MUTE_SECONDS",
    "PACK_DIR",
    "PACK_LIST",
    "PACK_PENDING_BYTES",
    "PACK_SHORT_SECONDS",
    "PILOT_TIMEOUT",
    "PLAYING_FLAG",
    "PROBE_KEPT",
    "PROBE_TIMEOUT",
    "RECODE_CODECS",
    "RECODE_DIR",
    "RUNTIME_GUESS",
    "SEEK_SHIFT",
    "SHRINK_DIR",
    "SPLIT_SLACK",
    "STEP_FOREIGN",
    "STEP_ORIGINAL",
    "STEP_RU_PLAIN",
    "STEP_SERVICE",
    "STUDIOS",
    "TIMELINE_ENV",
    "TS_OVERHEAD",
    "TYPE_CHECKING",
    "VOICE_KINDS",
    "WARM_TIMEOUT",
    "_DEPTH_FMT",
    "_DEPTH_PROFILE",
    "_FOREIGN_TITLE_RE",
    "_ORIGINAL_RE",
    "_PASS_ENV",
    "_RU_LANG",
    "_RU_TITLE_RE",
    "_SEEK_LOCK",
    "_SEEK_OK",
    "_SEGMENT_RE",
    "_SERVICE_RE",
    "_TECH_RE",
    "_TIMEOUT",
    "_UNIT_NAME",
    "_UNIT_TAG",
    "_VAGUE_LANG",
    "_VOICE_STEPS",
    "_WORDS_RE",
    "Any",
    "AudioTrack",
    "ContactWait",
    "Final",
    "InfraError",
    "Media",
    "Profile",
    "ServerDownError",
    "Studio",
    "SwarmError",
    "TorrFile",
    "TorrServer",
    "Warmup",
    "_file_stats",
    "bitrate_mbit",
    "codec_name",
    "color_depth",
    "dataclass",
    "quote",
    "re",
    "recode_note",
    "recodes_whole",
    "studio_of",
    "swarm_alive",
    "threading",
    "time",
    "voice_order",
    "why",
]

import re
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from torrcast import InfraError, SwarmError, why
from torrcast.profile import CAUTIOUS, COPY, Profile
from torrcast.timing import TIMELINE_ENV

#: Правило сверено с фактом на этом файле - пробный прогон (:func:`pack_start`) ему больше
#: не нужен. Ключ - URL потока, как и у кэша карты. Значение ``False`` - карта с фактом
#: разошлась, и дальше по этому файлу заходим только пробным прогоном.
_SEEK_OK: dict[str, bool] = {}
_SEEK_LOCK: Final = threading.Lock()
#: Начало ленты по фильмам: ``URL -> сдвиг`` (:func:`pack_origin`). Считается один раз на
#: файл, потому что заходов на него много (старт, перемотка, прогрев, перекод), а сдвиг
#: у них обязан быть ОДИН.
_ORIGIN: dict[str, float] = {}
_ORIGIN_LOCK: Final = threading.Lock()
