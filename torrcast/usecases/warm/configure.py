"""Подключает прогреву его внешний мир одним вызовом.

Зовёт композиционный корень (:mod:`torrcast.runtime.wire`) на запуске, и только он.
"""

from __future__ import annotations

import torrcast.usecases.warm._state as _state
from torrcast.ports.warm_environment.warm_environment import WarmEnvironment


def configure(environment: WarmEnvironment) -> None:
    """Передать сценарию часы, файловую операцию и телеметрию."""
    _state._environment = environment
    _state.segment_name = environment.segment_name
    _state.segment_slot = environment.segment_slot
    _state._hms = environment.hms
    _state.Packer = environment.packer_type
    _state.ffmpeg_pack_command = environment.pack_command
    _state.pack_start = environment.pack_start
    _state.spot_out = environment.spot_out
    _state.AUDIO_MBIT = environment.audio_mbit
    _state.TS_OVERHEAD = environment.ts_overhead
