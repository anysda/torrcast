"""Подключает подаче потока её внешний мир одним вызовом.

Зовёт композиционный корень (:mod:`torrcast.runtime.wire`) на запуске, и только он.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import torrcast.usecases.feed_pack._state as _state
from torrcast.ports.feed_clock import FeedClock
from torrcast.ports.pack_run.pack_factory import PackFactory


def configure(
    segment_name: Callable[[int], str],
    segment_slot: Callable[[str], int],
    settle_start: Callable[..., tuple[float, float]],
    pack_command: Callable[..., list[str]],
    packer: PackFactory,
    forget_flag: Callable[[Path], None],
    recode_dir: str,
    remove_tree: Callable[[Path], None],
    segment_paths: Callable[[Path], list[Path]],
    clock: FeedClock,
    spawn: Callable[[Callable[[], None]], None],
) -> None:
    """Передать сценарию имена сегментов, медиатракт упаковки, уборку, часы и подъём в стороне."""
    _state.segment_name = segment_name
    _state.segment_slot = segment_slot
    _state.settle_start = settle_start
    _state.ffmpeg_pack_command = pack_command
    _state.Packer = packer
    _state.forget_playing = forget_flag
    _state.RECODE_DIR = recode_dir
    _state.remove_tree = remove_tree
    _state.segment_paths = segment_paths
    _state.clock_port = clock
    _state.spawn = spawn
