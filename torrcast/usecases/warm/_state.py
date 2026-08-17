"""Внешний мир прогрева под прежними именами: часы, диск, телеметрия и медиатракт.

Заполняет слоты :func:`torrcast.usecases.warm.configure.configure`, читают их все
модули пакета - и читают в момент работы, а не на импорте.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.ports.warm_environment import WarmEnvironment, WarmGrid

Grid = WarmGrid
segment_name: Callable[[int], str]
segment_slot: Callable[[str], int]
_hms: Callable[[float], str]
Packer: Any
ffmpeg_pack_command: Any
pack_start: Any
AUDIO_MBIT: float
MAX_SEGMENT_BYTES: int
TS_OVERHEAD: float

_environment: WarmEnvironment
