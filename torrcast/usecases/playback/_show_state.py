"""Внешний мир показа: медиатракт, приёмник, часы и юнит - одним местом на всех.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) одним словом
(:func:`_configure_playback`) и одним договором
(:class:`torrcast.usecases.playback.show_environment.ShowEnvironment`); читают все части
сценария показа.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.clock import Clock
from torrcast.ports.prober import Prober
from torrcast.ports.receivers import Receivers
from torrcast.usecases.playback.heavy_profiles import HeavyProfileFlat, HeavyProfileOf
from torrcast.usecases.playback.media_grids import MediaGrids
from torrcast.usecases.playback.show_environment import ShowEnvironment
from torrcast.usecases.playback.spot_encodings import SpotEncodings
from torrcast.usecases.playback.spot_recoders import SpotRecoders
from torrcast.usecases.playback.stream_servers import StreamServers
from torrcast.usecases.playback.whole_encodings import WholeEncodings

#: Внешний мир показа. Всё это кладёт композиционный корень
#: (:mod:`torrcast.runtime.wire`): медиатракт, приёмник, часы и юнит показа - это сеть,
#: диск и подпроцессы, и называть их модули слою сценариев нечем. Имена оставлены теми
#: же, какими показ звал их всегда: меняется не вызов, а то, откуда берётся зависимость.
CLOCK: Clock
make_receiver: Receivers
probe: Prober
detect_profile: Callable[[Config], Choice]
pick_video_file: Callable[[list[TorrFile]], TorrFile]
hls_dir: Callable[[str], Path]
hls_base: Callable[[Config], str]
playing_flag: Callable[[Path], Path]
forget_playing: Callable[[Path], None]
start_play_unit: Callable[[str], None]
grid_for: MediaGrids
#: Раздача по http (:class:`torrcast.adapters.http_server.hls_server.HlsServer`), оба
#: кодировщика (:class:`torrcast.adapters.recode.encode.Encode`,
#: :class:`torrcast.adapters.recode.recoder.Recoder`), профиль тяжести
#: (:class:`torrcast.adapters.recode.weights.Weights`) и сплошной перекод: классы адаптеров, у
#: которых в слое сценариев есть только имя.
HlsServer: StreamServers
Encode: SpotEncodings
Recoder: SpotRecoders
#: Завод профиля тяжести - уже ГОТОВАЯ ручка ``Weights.of``, а не класс: показ зовёт
#: у неё ровно одно, и называть слоем сценариев весь класс адаптера незачем.
weights_of: HeavyProfileOf
#: Ровный профиль тяжести на случай, когда карты нет вовсе
#: (:meth:`torrcast.adapters.recode.weights.Weights.flat`) - такая же готовая ручка.
flat_weights: HeavyProfileFlat
whole_encode: WholeEncodings
#: Мгновенный потолок кодера сверх цели
#: (:data:`torrcast.adapters.recode.encode_settings.MAXRATE_GAIN`) и имя каталога перекодированных
#: кусков (:data:`torrcast.adapters.recode.recode_dir.RECODE_DIR`).
MAXRATE_GAIN: float
RECODE_DIR: str


def _configure_playback(environment: ShowEnvironment) -> None:
    """Назначить показу его внешний мир: медиатракт, приёмник, часы и юнит.

    Среда приходит одним договором, а не двумя десятками доводов по порядку: слот тут
    берётся по имени, и подать вместо него соседа того же рода нечем.
    """
    global CLOCK, make_receiver, probe, detect_profile, pick_video_file, hls_dir, hls_base
    global playing_flag, forget_playing, start_play_unit, grid_for, HlsServer
    global Encode, Recoder, weights_of, flat_weights, whole_encode, MAXRATE_GAIN, RECODE_DIR
    CLOCK = environment.clock
    make_receiver = environment.receivers
    probe = environment.prober
    detect_profile = environment.detect
    pick_video_file = environment.video_pick
    hls_dir = environment.out_dir
    hls_base = environment.base_url
    playing_flag = environment.flag
    forget_playing = environment.forget_flag
    start_play_unit = environment.start_unit
    grid_for = environment.grid
    HlsServer = environment.server
    Encode = environment.encode
    Recoder = environment.recoder
    weights_of = environment.weights
    flat_weights = environment.flat
    whole_encode = environment.whole
    MAXRATE_GAIN = environment.maxrate_gain
    RECODE_DIR = environment.recode_dir
