"""CLI — единственный наш процесс.
Контракт: ``cast <запрос> [sNeM] [--new] [--dry]``; ручки ``--release N``,
``--file N``, ``--voice N``, ``releases``, ``voices``, ``stop``, ``status``, ``doctor``,
``--tv``. Коды: ``0`` ок · ``1`` не нашли · ``2`` инфра-ошибка; наружу - короткие
русские строки без трейсбеков.

Счастливый путь — **один вопрос** и ни одного упоминания файлов: «какой фильм
франшизы?», и тот пропускается, когда картина одна. Релиз и озвучка выбираются сами,
о выборе говорится вслух, а таблица релизов, список файлов и меню озвучек уезжают в
отладочные ручки. Начатая картина продолжается молча; место видно в строке показа.
"""

from __future__ import annotations

__all__ = [
    "ALIVE_SEEDERS",
    "CTL_ENV",
    "EXIT_INFRA",
    "EXIT_NOT_FOUND",
    "EXIT_OK",
    "EXTRAS_MBIT",
    "FULL_HD_LIVENESS",
    "FULL_HEIGHT",
    "GATE_LIVENESS",
    "HD_HEIGHT",
    "HONEST_BUDGET",
    "HONEST_RATIO",
    "KEYS_WAIT",
    "MAX_LIVE",
    "MAX_TRIES",
    "META_BUDGET",
    "PAUSE_LIMIT",
    "PAUSE_SECONDS",
    "PEER_GRACE",
    "PICK_BUDGET",
    "PILOT_TIMEOUT",
    "PREWARM",
    "PREWARM_DUB",
    "PREWARM_SPARE",
    "PROBE_BUDGET",
    "PROBE_TIMEOUT",
    "REVIVE_DROP",
    "REVIVE_LIMIT",
    "REVIVE_LIVED",
    "REVIVE_PAUSE",
    "REVIVE_TRIES",
    "SAY_SECONDS",
    "SD_BITRATE",
    "SEASON_EPISODES",
    "SOUND_LIVENESS",
    "SOURCE_PAUSE",
    "SOURCE_TRIES",
    "START_BUDGET",
    "START_SLACK",
    "STEP_GRACE",
    "SWARM_GRACE",
    "TABLE_LIMIT",
    "TRACE_ENV",
    "TV_MENU",
    "VERDICT_BUDGET",
    "VOICE_MENU",
    "WARMED_RATIO",
    "WATCH_SECONDS",
    "WORKER_DUR",
    "WORKER_META",
    "_BTIH",
    "_DISC_RE",
    "Args",
    "ChromecastReceiver",
    "Config",
    "Device",
    "Entry",
    "Episode",
    "Facts",
    "InfraError",
    "NotFoundError",
    "Profile",
    "Progress",
    "Receiver",
    "Sequence",
    "State",
    "Supply",
    "TorrcastError",
    "TorrServer",
    "Watch",
    "_Clock",
    "_Stopped",
    "__version__",
    "_cache_reserve",
    "_cmd_configure",
    "_cmd_doctor",
    "_cmd_log",
    "_cmd_releases",
    "_cmd_status",
    "_cmd_stop",
    "_cmd_voices",
    "_cmd_worker",
    "_duration",
    "_following",
    "_held_by_show",
    "_on_term",
    "_own_torrent",
    "_release_orphans",
    "_release_torrents",
    "_say_showing",
    "_since_seconds",
    "_torrent_hash",
    "_worker_loop",
    "argparse",
    "ask",
    "console",
    "contextlib",
    "dataclass",
    "detect_profile",
    "hls_base",
    "io",
    "load_config",
    "make_receiver",
    "mark",
    "parse_args",
    "partial",
    "probe",
    "re",
    "save_config",
    "scan",
    "signal",
    "split_episode",
    "stop_play_unit",
    "sys",
    "terminal",
    "trace",
    "trace_thresholds",
    "tune_profile",
    "unit_active",
    "unit_key",
]

import argparse
import contextlib
import io
import re
import signal
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from functools import partial

from torrcast import (
    InfraError,
    NotFoundError,
    TorrcastError,
    __version__,
    console,  # через модуль: терминал спрашиваем там же, где и сами вопросы
    scan,  # через модуль: поиск приёмников тесты подменяют целиком
    trace,
)
from torrcast.cast import ChromecastReceiver, Receiver, make_receiver

# Разложенные по слоям сценарии читают пороги отсюда прямо на своём импорте, поэтому
# стоят они ниже порогов, а не в общей шапке. Разбор аргументов уехал в слой команд,
# и реэкспорт его имён стоит там же: на них ссылаются .pyi перенесённых сценариев.
from torrcast.cli.args import Args
from torrcast.cli.parse_args import TV_MENU, parse_args
from torrcast.console import Progress, ask, terminal
from torrcast.domain.debug_handles import CTL_ENV, TRACE_ENV
from torrcast.domain.exit_codes import EXIT_INFRA, EXIT_NOT_FOUND, EXIT_OK
from torrcast.domain.pick_settings import (
    HONEST_BUDGET,
    MAX_TRIES,
    META_BUDGET,
    PICK_BUDGET,
    PROBE_BUDGET,
    SWARM_GRACE,
    VERDICT_BUDGET,
)
from torrcast.domain.prewarm_settings import MAX_LIVE, PREWARM, PREWARM_DUB, PREWARM_SPARE
from torrcast.domain.rank_settings import (
    ALIVE_SEEDERS,
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
from torrcast.domain.rank_settings import (
    DISC_RE as _DISC_RE,
)
from torrcast.domain.revive_settings import (
    REVIVE_DROP,
    REVIVE_LIMIT,
    REVIVE_LIVED,
    REVIVE_PAUSE,
    REVIVE_TRIES,
    SOURCE_PAUSE,
    SOURCE_TRIES,
)
from torrcast.domain.start_settings import (
    PAUSE_LIMIT,
    PAUSE_SECONDS,
    SAY_SECONDS,
    START_SLACK,
)
from torrcast.facts import Facts
from torrcast.parse import Episode, split_episode
from torrcast.profile import Profile, trace_thresholds
from torrcast.profile import detect as detect_profile
from torrcast.profile import tune as tune_profile
from torrcast.runtime.configure_command import configure_command as _cmd_configure
from torrcast.runtime.status_command import status_command as _cmd_status
from torrcast.runtime.stop_command import stop_command as _cmd_stop
from torrcast.scan import Device
from torrcast.state import Config, Entry, State, load_config, save_config
from torrcast.stream import (
    KEYS_WAIT,
    PILOT_TIMEOUT,
    PROBE_TIMEOUT,
    Supply,
    TorrServer,
    hls_base,
    probe,
    stop_play_unit,
    unit_active,
    unit_key,
)
from torrcast.timing import mark
from torrcast.usecases.cache_reserve import _cache_reserve
from torrcast.usecases.doctor_command import _cmd_doctor
from torrcast.usecases.episode_duration import WORKER_DUR, _duration
from torrcast.usecases.log_command import _cmd_log, _since_seconds
from torrcast.usecases.releases_command import _cmd_releases
from torrcast.usecases.say_showing import _say_showing
from torrcast.usecases.start_budget import START_BUDGET
from torrcast.usecases.start_clock import _Clock
from torrcast.usecases.status import WARMED_RATIO
from torrcast.usecases.stopped import _on_term, _Stopped
from torrcast.usecases.torrents import (
    _BTIH,
    _held_by_show,
    _own_torrent,
    _release_orphans,
    _release_torrents,
    _torrent_hash,
)
from torrcast.usecases.voices_command import _cmd_voices
from torrcast.usecases.watch import WATCH_SECONDS, Watch
from torrcast.usecases.worker import _cmd_worker
from torrcast.usecases.worker_loop import WORKER_META, _following, _worker_loop

__all__ = [name for name in globals() if not name.startswith("__")]
