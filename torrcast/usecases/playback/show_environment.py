"""Внешний мир показа одним договором: медиатракт, приёмник, часы и юнит показа.

Собирает его композиционный корень (:mod:`torrcast.runtime.wire_show`), а по слотам
сценария раскладывает :func:`torrcast.usecases.playback._show_state._configure_playback`.

Имена полей сняты с настоящих вызовов показа, а роды - с уже названных договоров:
сетка, раздача, оба кодировщика и профиль тяжести приходят своими протоколами, а не
родом «что угодно». Поля названные и только названные: собрать среду по порядку нельзя,
поэтому перепутать местами два слота одного рода при сборке не выйдет вовсе.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from torrcast.domain.choice import Choice
from torrcast.domain.config import Config
from torrcast.domain.film_keys import FilmKeys
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.clock import Clock
from torrcast.ports.prober import Prober
from torrcast.ports.receivers import Receivers
from torrcast.usecases.playback.heavy_profiles import HeavyProfileFlat, HeavyProfileOf
from torrcast.usecases.playback.media_grids import MediaGrids
from torrcast.usecases.playback.spot_encodings import SpotEncodings
from torrcast.usecases.playback.spot_recoders import SpotRecoders
from torrcast.usecases.playback.stream_servers import StreamServers
from torrcast.usecases.playback.whole_encodings import WholeEncodings


@dataclass(frozen=True, slots=True, kw_only=True)
class ShowEnvironment:
    """Всё, чего показ сам не умеет: сеть, диск, подпроцессы и часы."""

    #: Часы показа, завод приёмника и паспорт файла.
    clock: Clock
    receivers: Receivers
    prober: Prober
    #: Паспорт приёмника по настройкам и выбор видеофайла в раздаче.
    detect: Callable[[Config], Choice]
    video_pick: Callable[[list[TorrFile]], TorrFile]
    #: Каталог упакованного и свой адрес в сторону телевизора.
    out_dir: Callable[[str], Path]
    base_url: Callable[[Config], str]
    #: Отметка «идёт показ»: где лежит и как её снять.
    flag: Callable[[Path], Path]
    forget_flag: Callable[[Path], None]
    #: Подъём юнита показа и карта опорных кадров файла.
    start_unit: Callable[[str], None]
    keys: Callable[[str], FilmKeys]
    #: Медиатракт: сетка сегментов, раздача по http и оба кодировщика.
    grid: MediaGrids
    server: StreamServers
    encode: SpotEncodings
    recoder: SpotRecoders
    #: Профиль тяжести по карте и ровный профиль на случай, когда карты нет вовсе.
    weights: HeavyProfileOf
    flat: HeavyProfileFlat
    whole: WholeEncodings
    #: Мгновенный потолок кодера сверх цели и имя каталога перекодированных кусков.
    maxrate_gain: float
    recode_dir: str
