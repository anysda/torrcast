"""Собирает сеанс показа из прежней машинерии: юнита, состояния и службы раздач.
Берут его отсюда команды ``cast stop`` и ``cast status``.
"""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.browser.read_web_box import read_web_box
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.adapters.unit_playback_session import UnitPlaybackSession
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError
from torrcast.ports.show_unit.slot import unit
from torrcast.ports.state_store.slot import store
from torrcast.usecases.cache_reserve import _cache_reserve
from torrcast.usecases.playback.hls_root import hls_root
from torrcast.usecases.torrents import _release_torrents


def _stream_address(config: Config) -> str:
    """Откуда забирают поток: маршрут до ТВ, а у показа вкладки - адрес из её ящика.

    Показ ``--here`` играет у просившего, и ``tv`` в настройках машины при этом может
    быть пустым: маршрута до приёмника нет, а раздача есть, и свой адрес показ уже
    положил в ящик вкладки (:mod:`torrcast.adapters.browser.write_web_box`). Без этого
    кадр играющей картины на машине без телевизора не снять: файл настроек про
    ``receiver: browser`` этого запуска не знает. Ящик пуст - вкладки нет, и отказ
    маршрута остаётся отказом.
    """
    try:
        return hls_base(config)
    except InfraError:
        box = read_web_box(hls_root(config.hls_dir))
        url = str(box.get("url", ""))
        if not url:
            raise
        return url


def playback_session(configuration: Callable[[], Config] | None = None) -> UnitPlaybackSession:
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
        stream_address=_stream_address,
    )
