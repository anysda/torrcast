"""Внешний мир прогрева под прежними именами: часы, диск, телеметрия и медиатракт.

Заполняет слоты :func:`torrcast.usecases.warm.configure.configure`, читают их все
модули пакета - и читают в момент работы, а не на импорте.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.ports.warm_environment import WarmEnvironment, WarmGrid, WarmPack, WarmPacker

Grid = WarmGrid
#: Прогон упаковки в том объёме, в каком его знает прогрев: край, процесс, выкладка и
#: конец. Договор стоит в порту (:class:`torrcast.ports.warm_environment.WarmPack`), а
#: не повторяется здесь: повторённый, он разъезжался бы с портом молча.
_Run = WarmPack

segment_name: Callable[[int], str]
segment_slot: Callable[[str], int]
_hms: Callable[[float], str]
#: Медиатракт прогрева: завод захода упаковки, сборка команды ffmpeg и пробный прогон.
#: Кладёт их :func:`configure` из среды (:class:`...warm_environment.WarmEnvironment`),
#: и там же названы их договоры - здесь стоят ровно они.
Packer: WarmPacker
ffmpeg_pack_command: Callable[..., list[str]]
pack_start: Callable[[str, float], float]
AUDIO_MBIT: float
MAX_SEGMENT_BYTES: int
TS_OVERHEAD: float

_environment: WarmEnvironment
