"""Часть CLI; публичный фасад - :mod:`torrcast.cli`.

Реэкспорт отбора: план картины, подготовка релиза и выбор озвучки. Ни строчки логики -
каждая единица живёт в своём файле.

⚠️ Продолжение показа (:func:`~torrcast.usecases.select._continue._continue`) отсюда не
реэкспортится намеренно: оно единственное в отборе зовёт показ, и втянутое сюда
замыкало бы два пакета друг на друга - порядок импортов решал бы, поднимется ли
приложение вообще. Зовущие называют его домом.
"""

from __future__ import annotations

from dataclasses import field

from torrcast.domain._series import _Series
from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.episode import Episode
from torrcast.domain.episode_file import EpisodeFile
from torrcast.domain.exit_codes import EXIT_OK
from torrcast.domain.infra_error import InfraError
from torrcast.domain.map_episodes import map_episodes
from torrcast.domain.media import Media
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.pick_settings import META_BUDGET, PROBE_BUDGET
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, COPY, REFUSE, Profile
from torrcast.domain.recode_note import recode_note
from torrcast.domain.recode_settings import RECODE_HEIGHT
from torrcast.domain.release import Release
from torrcast.domain.server_down_error import ServerDownError
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.torr_file import TorrFile
from torrcast.domain.watch_state import WatchState
from torrcast.ports.progress import Progress
from torrcast.usecases.select._about import _about
from torrcast.usecases.select._nothing_late import _nothing_late
from torrcast.usecases.select._pick_state import _configure_select
from torrcast.usecases.select._prep import _Prep
from torrcast.usecases.select._remembered import _remembered
from torrcast.usecases.select._verdict import (
    _did_not_answer,
    _silenced,
    _turned_down,
    _waiting_note,
)
from torrcast.usecases.select._voiced import _revoice, _Voiced, _voiced
from torrcast.usecases.select.plan import Plan
from torrcast.usecases.select.select import Select

__all__ = [
    "CAUTIOUS",
    "COPY",
    "EXIT_OK",
    "META_BUDGET",
    "PROBE_BUDGET",
    "RECODE_HEIGHT",
    "REFUSE",
    "Config",
    "Entry",
    "Episode",
    "EpisodeFile",
    "InfraError",
    "Media",
    "NotFoundError",
    "Picture",
    "Plan",
    "Profile",
    "Progress",
    "Release",
    "Select",
    "ServerDownError",
    "SwarmError",
    "TorrcastError",
    "TorrFile",
    "WatchState",
    "_Prep",
    "_Series",
    "_Voiced",
    "_about",
    "_configure_select",
    "_did_not_answer",
    "_nothing_late",
    "_remembered",
    "_revoice",
    "_silenced",
    "_turned_down",
    "_voiced",
    "_waiting_note",
    "field",
    "map_episodes",
    "recode_note",
]
