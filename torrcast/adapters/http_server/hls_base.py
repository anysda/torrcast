"""Собирает базу URL раздачи для приёмника; зовут показ и щуп раздачи."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.http_server.our_address import our_address
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError


def hls_base(config: Config, route: Callable[[str], str] = our_address) -> str:
    """База URL, под которой ТВ забирает манифест и сегменты.

    Имени здесь нет и быть не должно: адрес собирается из транспорта, нашего адреса со
    стороны ТВ и порта — DNS в пути показа не участвует. ``hls_base_url`` в конфиге,
    если он задан, перебивает всё: это запасной выход на случай, когда прямой путь
    почему-то не работает.

    ``route`` - чем спрашивается свой адрес в сторону ТВ. Умолчание боевое
    (:func:`~torrcast.adapters.http_server.our_address.our_address`), и меняет его только
    стенд: настоящий ответ зависит от таблицы маршрутов машины, где идёт прогон.
    """
    if config.hls_base_url:
        return config.hls_base_url.rstrip("/")
    host = route(config.tv or "")
    if not host:
        tv = config.tv or phrase("http_server.address_unset")
        raise InfraError(phrase("http_server.no_route_to_tv", tv=tv))
    return f"{config.transport}://{host}:{config.hls_port}"
