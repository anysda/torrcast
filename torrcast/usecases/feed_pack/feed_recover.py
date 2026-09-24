"""Reopen a silent live reader without blocking the playback clock."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack._state as _state
from torrcast.domain.hls_settings import MUTE_SECONDS
from torrcast.ports.journal.slot import journal

if TYPE_CHECKING:
    from collections.abc import Callable

    from torrcast.usecases.feed_pack.feed_state import _State


def _recover(state: _State, lift: Callable[[int], None]) -> None:
    """An open process is not evidence that its HTTP read will ever finish.

    The source may accept new reads while an old TorrServer request stays stuck.
    Reopen at the first unpublished segment, retaining the delivered files. The
    replacement gets a full silence interval too; retries do not condemn a slot.
    ``lift`` owns the acquired lock and releases it when the new reader is ready.
    """
    packer = state.packer
    if not state.offline or state.fatal or packer is None or packer.halted or packer.finished():
        return
    now = _state.clock_port.monotonic()
    if now - max(state.moved, state.restarted) <= MUTE_SECONDS:
        return
    if not state.lock.acquire(blocking=False):
        return
    handed = False
    try:
        if state.packer is not packer or now - max(state.moved, state.restarted) <= MUTE_SECONDS:
            return  # a concurrent request already supplied bytes or replaced the reader
        slot = packer.edge + 1
        state.restarted = now
        journal().mark("повтор чтения молчащего источника", слот=slot)
        _state.spawn(lambda: lift(slot))
        handed = True
    finally:
        if not handed:
            state.lock.release()
