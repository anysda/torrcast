"""Внешний мир прогрева под прежними именами: часы, диск, телеметрия и медиатракт.

Заполняет слоты :func:`torrcast.usecases.warm.configure.configure`, читают их все
модули пакета - и читают в момент работы, а не на импорте.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, Protocol

from torrcast.ports.warm_environment import WarmEnvironment, WarmGrid

Grid = WarmGrid


class _Signalled(Protocol):
    """Процесс прогона в том объёме, в каком его знает прогрев: ему шлют сигнал."""

    def send_signal(self, number: int) -> None: ...


class _Run(Protocol):
    """Прогон упаковки в объёме, в каком его знает прогрев: край, выкладка и конец."""

    #: Последний сегмент, который этот прогон выложил наружу.
    edge: int

    @property
    def proc(self) -> _Signalled: ...

    def publish(self) -> None: ...
    def poll(self) -> int | None: ...
    def stop(self, keep_files: bool = False, reason: str = "") -> None: ...


segment_name: Callable[[int], str]
segment_slot: Callable[[str], int]
_hms: Callable[[float], str]
# ⚠️ Три слота ниже названы `Any` не по недосмотру. Кладёт их :func:`configure` из
# среды прогрева (:class:`torrcast.ports.warm_environment.WarmEnvironment`), а порт
# называет их `object`: класс прогона упаковки и обе ручки медиатракта - адаптерные, и
# из порта их имена не видны. Честно назвать их можно ровно там, где среда объявлена, -
# в самом порту; здесь любое имя было бы куплено приведением на входе.
Packer: Any
ffmpeg_pack_command: Any
pack_start: Any
AUDIO_MBIT: float
MAX_SEGMENT_BYTES: int
TS_OVERHEAD: float

_environment: WarmEnvironment
