"""Уступить подъём показа чужому запуску, не трогая его юнит."""

from __future__ import annotations

from torrcast.domain.cancelled_error import CancelledError
from torrcast.domain.catalogs.phrase import phrase
from torrcast.ports.progress.progress import Progress
from torrcast.usecases.playback.launch_owner import LaunchOwner

__all__ = ["yield_to_other"]


def yield_to_other(owner: LaunchOwner | None, progress: Progress) -> None:
    """Подъём снят чужим запуском - кончить ожидание отменой, не трогая чужой юнит."""
    if owner is not None and owner.taken_over():
        progress.phase("")
        raise CancelledError(phrase("playback.abandoned"))
