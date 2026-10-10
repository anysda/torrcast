"""Ожидание файлов раздачи с контрактом ``ContactWait``."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from torrcast.adapters.torrserver.contact_wait import ContactWait
from torrcast.adapters.torrserver.file_stats import file_stats
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.swarm_alive import swarm_alive
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.contact_wait import ContactWait as ContactWaitPort

if TYPE_CHECKING:
    from torrcast.ports.clock import Clock


META_STEP = 0.05
META_STEP_GROW = 1.5
META_STEP_MAX = 0.2


def wait_files(
    status: Callable[[str], dict[str, Any]],
    torrent_hash: str,
    timeout: float,
    grace: float | ContactWaitPort,
    clock: Clock,
) -> list[TorrFile]:
    """Дождаться файлов, не начиная бюджет прогрева заново."""
    began = clock.monotonic()
    deadline = began + timeout
    hopeless = began + float(grace)
    empty_since: float | None = None
    step = META_STEP
    while True:
        payload = status(torrent_hash)
        files = file_stats(payload)
        if files:
            return files
        now = clock.monotonic()
        if swarm_alive(payload) is False:
            empty_since = now if empty_since is None else empty_since
        else:  # хоть один контакт был - отсрочка считается заново от этой секунды
            empty_since = None
        if isinstance(grace, ContactWait):
            activated = grace.activated_at
            if activated is None:
                clock.sleep(min(step, META_STEP_MAX))
                step = min(step * META_STEP_GROW, META_STEP_MAX)
                continue
            # 🔴 TC-739. Прогрев спрашивает рой с той секунды, как раздача добавлена,
            # а не с той, как до неё дошла очередь: своё ожидание он уже отстоял, и
            # начинать бюджеты заново значит ждать по второму разу то же самое.
            # Приговор при этом не выносится раньше вопроса: до него релиз никому не
            # мешает, и объявлять его негодным незачем.
            deadline = max(activated, began + timeout)
            empty_at = empty_since if empty_since is not None else now
            hopeless = max(activated, empty_at + grace.seconds)
        seconds = grace.seconds if isinstance(grace, ContactWait) else float(grace)
        if seconds > 0 and now >= hopeless and swarm_alive(payload) is False:
            raise SwarmError(
                phrase("torrserver.swarm_empty", seconds=f"{seconds:.0f}"), waited=seconds
            )
        left = deadline - now
        if left <= 0:
            raise SwarmError(
                phrase("torrserver.metadata_timeout", timeout=f"{timeout:.0f}"), waited=timeout
            )
        clock.sleep(min(step, left))
        step = min(step * META_STEP_GROW, META_STEP_MAX)


__all__ = ["wait_files"]
