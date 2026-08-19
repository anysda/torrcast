"""Реэкспорт сценария показа: запуск, тракт, прогрев и конец показа.

Ни строчки логики - каждая часть живёт в своём файле пакета. Прежние имена собраны
здесь потому, что плоский namespace прежнего монолита (:mod:`torrcast.cli`) спрашивает
их у одного модуля.
"""

from __future__ import annotations

import contextlib as contextlib
from collections.abc import Callable as Callable
from pathlib import Path as Path
from typing import Any as Any
from typing import NoReturn as NoReturn
from typing import Protocol as Protocol
from typing import runtime_checkable as runtime_checkable

from torrcast.domain._name_data.data_3 import VIDEO_EXT as VIDEO_EXT
from torrcast.domain.choice import Choice as Choice
from torrcast.domain.codec_name import codec_name as codec_name
from torrcast.domain.config import Config as Config
from torrcast.domain.entry import ENDING_RATIO as ENDING_RATIO
from torrcast.domain.entry import Entry as Entry
from torrcast.domain.exit_codes import EXIT_OK as EXIT_OK
from torrcast.domain.film_keys import FilmKeys as FilmKeys
from torrcast.domain.infra_error import InfraError as InfraError
from torrcast.domain.media import AUDIO_MBIT as AUDIO_MBIT
from torrcast.domain.media import TS_OVERHEAD as TS_OVERHEAD
from torrcast.domain.not_found_error import NotFoundError as NotFoundError
from torrcast.domain.profile import CAUTIOUS as CAUTIOUS
from torrcast.domain.profile import Profile as Profile
from torrcast.domain.recode_note import recode_note as recode_note
from torrcast.domain.recodes_whole import recodes_whole as recodes_whole
from torrcast.domain.release import Release as Release
from torrcast.domain.revive_settings import REVIVE_DROP as REVIVE_DROP
from torrcast.domain.revive_settings import REVIVE_LIMIT as REVIVE_LIMIT
from torrcast.domain.revive_settings import REVIVE_LIVED as REVIVE_LIVED
from torrcast.domain.revive_settings import REVIVE_PAUSE as REVIVE_PAUSE
from torrcast.domain.revive_settings import REVIVE_TRIES as REVIVE_TRIES
from torrcast.domain.start_refused_error import StartRefusedError as StartRefusedError
from torrcast.domain.torrcast_error import TorrcastError as TorrcastError
from torrcast.domain.torr_file import TorrFile as TorrFile
from torrcast.domain.why import why as why
from torrcast.domain.worker_settings import WORKER_DUR as WORKER_DUR
from torrcast.ports.clock import Clock as Clock
from torrcast.ports.journal import journal as journal
from torrcast.ports.prober import Prober as Prober
from torrcast.ports.progress import Progress as Progress
from torrcast.ports.progress import progress as progress_bar
from torrcast.ports.receiver import Receiver as Receiver
from torrcast.ports.receivers import Receivers as Receivers
from torrcast.ports.recode.encoding import Encoding as Encoding
from torrcast.ports.recode.spot_recoder import SpotRecoder as SpotRecoder
from torrcast.ports.show_unit import ShowUnit as ShowUnit
from torrcast.ports.show_unit import unit as show_unit
from torrcast.ports.state_store import store as store
from torrcast.ports.stream_source import StreamSource as StreamSource
from torrcast.usecases.feed_pack import Feed as Feed
from torrcast.usecases.playback._cuttable import _Cuttable as _Cuttable
from torrcast.usecases.playback._encode_all import _encode_all as _encode_all
from torrcast.usecases.playback._launch import _await_playing as _await_playing
from torrcast.usecases.playback._launch import _launch as _launch
from torrcast.usecases.playback._launch import _refuse_hopeless as _refuse_hopeless
from torrcast.usecases.playback._launch import _resume as _resume
from torrcast.usecases.playback._numbered import _Numbered as _Numbered
from torrcast.usecases.playback._play import _play as _play
from torrcast.usecases.playback._recoder import _recoder as _recoder
from torrcast.usecases.playback._show_end import _blame_the_end as _blame_the_end
from torrcast.usecases.playback._show_end import _close_show as _close_show
from torrcast.usecases.playback._show_end import _handover as _handover
from torrcast.usecases.playback._show_end import _report_end as _report_end
from torrcast.usecases.playback._show_end import _say_whole as _say_whole
from torrcast.usecases.playback._show_state import _configure_playback as _configure_playback
from torrcast.usecases.playback._tract import _tract as _tract
from torrcast.usecases.playback._warmer import _next_warmer as _next_warmer
from torrcast.usecases.playback._warmer import _warmer as _warmer
from torrcast.usecases.playback.file_picker import _default_file as _default_file
from torrcast.usecases.playback.file_picker import file_picker as file_picker
from torrcast.usecases.playback.following import Following as Following
from torrcast.usecases.playback.heavy_profile import HeavyProfile as HeavyProfile
from torrcast.usecases.playback.heavy_profiles import HeavyProfileOf as HeavyProfileOf
from torrcast.usecases.playback.layout import layout as layout
from torrcast.usecases.playback.media_grid import MediaGrid as MediaGrid
from torrcast.usecases.playback.media_grids import MediaGrids as MediaGrids
from torrcast.usecases.playback.spot_encodings import SpotEncodings as SpotEncodings
from torrcast.usecases.playback.spot_recoders import SpotRecoders as SpotRecoders
from torrcast.usecases.playback.stream_server import StreamServer as StreamServer
from torrcast.usecases.playback.stream_servers import StreamServers as StreamServers
from torrcast.usecases.playback.whole_encodings import WholeEncodings as WholeEncodings
from torrcast.usecases.revive_playback import _hold as _hold
from torrcast.usecases.revive_playback import _Revival as _Revival
from torrcast.usecases.select._about import _about as _about
from torrcast.usecases.select.plan import Plan as Plan
from torrcast.usecases.source_blame import _asked as _asked
from torrcast.usecases.source_blame import _blamed as _blamed
from torrcast.usecases.start_budget import START_BUDGET as START_BUDGET
from torrcast.usecases.start_clock import _Clock as _Clock
from torrcast.usecases.warm import Vault as Vault
from torrcast.usecases.warm import Warmer as Warmer
from torrcast.usecases.warm import warm_key as warm_key
from torrcast.usecases.warm import warm_root as warm_root
from torrcast.usecases.watch import Watch as Watch

__all__ = ["progress_bar", "show_unit"]
