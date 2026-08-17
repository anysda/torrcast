"""Собирает базу URL раздачи для приёмника; зовут показ и щуп раздачи."""

from __future__ import annotations

from torrcast.adapters.filesystem.state import Config
from torrcast.adapters.http_server.our_address import our_address
from torrcast.domain.infra_error import InfraError


def hls_base(config: Config) -> str:
    """База URL, под которой ТВ забирает манифест и сегменты.

    Имени здесь нет и быть не должно: адрес собирается из транспорта, нашего адреса со
    стороны ТВ и порта — DNS в пути показа не участвует. ``hls_base_url`` в конфиге,
    если он задан, перебивает всё: это запасной выход на случай, когда прямой путь
    почему-то не работает.
    """
    if config.hls_base_url:
        return config.hls_base_url.rstrip("/")
    host = our_address(config.tv or "")
    if not host:
        raise InfraError(f"не вижу маршрута до ТВ {config.tv or '(адрес не задан)'}")
    return f"{config.transport}://{host}:{config.hls_port}"
