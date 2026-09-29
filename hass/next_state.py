"""``has_next`` снимка ``GET /api/state``: знает ли мост следующую серию."""

from __future__ import annotations

from typing import TYPE_CHECKING

from hass.following import _waits_for_next, following

if TYPE_CHECKING:
    from torrcast.ports.playback_session import PlaybackSession


def next_state(session: PlaybackSession) -> bool | None:
    """Серия названа - ``True``; ``None`` - стык ждёт поиска юнита; иначе ``False``."""
    if following(session) is not None:
        return True
    return None if _waits_for_next(session) else False


__all__ = ["next_state"]
