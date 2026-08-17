"""Собирает сеанс показа из прежней машинерии: юнита, состояния и службы раздач.
Берут его отсюда команды ``cast stop`` и ``cast status``.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from torrcast.adapters.filesystem.state import load_config
from torrcast.adapters.http_server.stream_serve import hls_base
from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.ports.show_unit import unit
from torrcast.ports.state_store import store
from torrcast.usecases.cache_reserve import _cache_reserve
from torrcast.usecases.torrents import _release_torrents


def playback_session(configuration: Callable[[], Any] | None = None) -> UnitPlaybackSession:
    """Сеанс показа со звеньями, взятыми из их настоящих домов.

    Собирает его корень - единственный слой, которому разрешено видеть адаптеры разом.
    Состояние приходит не адаптером, а портом: кто его хранит, решено выше по сборке
    (:func:`torrcast.runtime.wire.wire`), и здесь это уже не забота сеанса.
    """
    return UnitPlaybackSession(
        configuration=configuration if configuration is not None else load_config,
        state=lambda: store().load(),
        active=lambda: unit().active(),
        unit_key=lambda: unit().key(),
        stop_unit=lambda: unit().stop(),
        release_torrents=_release_torrents,
        cache_reserve=_cache_reserve,
        stream_address=hls_base,
    )
