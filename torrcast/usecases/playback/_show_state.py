"""Внешний мир показа: медиатракт, приёмник, часы и юнит - одним местом на всех.

Кладёт его композиционный корень (:mod:`torrcast.runtime.wire`) одним словом
(:func:`_configure_playback`); читают все части сценария показа.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.clock import Clock
from torrcast.ports.prober import Prober
from torrcast.ports.receivers import Receivers
from torrcast.usecases.playback.heavy_profiles import HeavyProfileOf
from torrcast.usecases.playback.media_grids import MediaGrids
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
film_keys: Callable[[str], FilmKeys]
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
whole_encode: WholeEncodings
#: Мгновенный потолок кодера сверх цели
#: (:data:`torrcast.adapters.recode.encode_settings.MAXRATE_GAIN`) и имя каталога перекодированных
#: кусков (:data:`torrcast.adapters.recode.recode_dir.RECODE_DIR`).
MAXRATE_GAIN: float
RECODE_DIR: str


def _configure_playback(
    clock: Clock,
    receivers: Receivers,
    prober: Prober,
    detect: Callable[[Config], Choice],
    video_pick: Callable[[list[TorrFile]], TorrFile],
    out_dir: Callable[[str], Path],
    base_url: Callable[[Config], str],
    flag: Callable[[Path], Path],
    forget_flag: Callable[[Path], None],
    start_unit: Callable[[str], None],
    keys: Callable[[str], FilmKeys],
    grid: MediaGrids,
    server: StreamServers,
    encode: SpotEncodings,
    recoder: SpotRecoders,
    weights: HeavyProfileOf,
    whole: WholeEncodings,
    maxrate_gain: float,
    recode_dir: str,
) -> None:
    """Назначить показу его внешний мир: медиатракт, приёмник, часы и юнит."""
    global CLOCK, make_receiver, probe, detect_profile, pick_video_file, hls_dir, hls_base
    global playing_flag, forget_playing, start_play_unit, film_keys, grid_for, HlsServer
    global Encode, Recoder, weights_of, whole_encode, MAXRATE_GAIN, RECODE_DIR
    CLOCK = clock
    make_receiver = receivers
    probe = prober
    detect_profile = detect
    pick_video_file = video_pick
    hls_dir = out_dir
    hls_base = base_url
    playing_flag = flag
    forget_playing = forget_flag
    start_play_unit = start_unit
    film_keys = keys
    grid_for = grid
    HlsServer = server
    Encode = encode
    Recoder = recoder
    weights_of = weights
    whole_encode = whole
    MAXRATE_GAIN = maxrate_gain
    RECODE_DIR = recode_dir
