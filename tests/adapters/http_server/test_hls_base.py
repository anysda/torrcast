"""Проверяет базу URL раздачи: имени в ней нет, а маршрут до ТВ обязателен."""

from __future__ import annotations

import pytest

from torrcast.adapters.http_server.hls_base import hls_base
from torrcast.domain.config import Config
from torrcast.domain.infra_error import InfraError


def test_the_base_is_built_from_the_transport_our_address_and_the_port() -> None:
    """DNS в пути показа не участвует: адрес собирается из транспорта, адреса и порта.

    Имя тут стоило бы показу отдельной точки отказа - ТВ ходит по IP и разрешать имена
    в сегменте телевизора некому.
    """
    config = Config(tv="10.0.100.9", transport="http", hls_port=8080)
    assert hls_base(config, lambda tv: "10.0.100.5") == "http://10.0.100.5:8080"


def test_the_configured_base_overrides_everything() -> None:
    """Запасной выход: заданная в конфиге база перебивает собранную и не спрашивает маршрут."""

    def never(tv: str) -> str:  # pragma: no cover - до него не доходит
        raise AssertionError("маршрут спрашивать незачем: база задана")

    config = Config(tv="10.0.100.9", hls_base_url="https://кино.дома:9443/")
    assert hls_base(config, never) == "https://кино.дома:9443"


def test_without_a_route_to_the_receiver_the_base_is_refused() -> None:
    """Маршрута нет - беда словами. Молча собранная база уводит показ в никуда."""
    with pytest.raises(InfraError, match="no route to the TV"):
        hls_base(Config(tv="10.0.100.9"), lambda tv: "")
    with pytest.raises(InfraError, match="address not set"):
        hls_base(Config(), lambda tv: "")
