"""Подключает подаче потока её внешний мир одним вызовом.

Зовёт композиционный корень (:mod:`torrcast.runtime.wire`) на запуске, и только он.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import torrcast.usecases.feed_pack._state as _state


def configure(
    segment_name: Callable[[int], str],
    segment_slot: Callable[[str], int],
    pack_start: Callable[..., float],
    pack_command: Callable[..., list[str]],
    forget_flag: Callable[[Path], None],
    recode_dir: str,
) -> None:
    """Передать сценарию имена сегментов, пробный прогон, упаковку и каталог перекода."""
    _state.segment_name = segment_name
    _state.segment_slot = segment_slot
    _state.pack_start = pack_start
    _state.ffmpeg_pack_command = pack_command
    _state.forget_playing = forget_flag
    _state.RECODE_DIR = recode_dir
