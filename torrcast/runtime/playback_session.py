"""Собирает сеанс показа из прежней машинерии: юнита, состояния и службы раздач.
Берут его отсюда команды ``cast stop`` и ``cast status``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.ports.module import module


def playback_session(configuration: Callable[[], Any] | None = None) -> UnitPlaybackSession:
    """Сеанс показа с зависимостями, взятыми у неразложенного модуля команд.

    Имена спрашиваются у модуля в момент сборки, а не связываются на импорте: так
    диагностическая или тестовая подмена одного звена доезжает до сценария целиком.
    """
    legacy = module("torrcast.commands")
    return UnitPlaybackSession(
        configuration=configuration if configuration is not None else legacy.load_config,
        state=legacy.State.load,
        active=legacy.unit_active,
        unit_key=legacy.unit_key,
        stop_unit=legacy.stop_play_unit,
        release_torrents=legacy._release_torrents,
        cache_reserve=legacy._cache_reserve,
        stream_address=legacy.hls_base,
    )
