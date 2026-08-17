"""Проверяет базу URL раздачи: имени в ней нет, а маршрут до ТВ обязателен."""

from __future__ import annotations

import pytest

from torrcast.adapters.filesystem.state import Config
from torrcast.adapters.http_server import hls_base as module
from torrcast.domain.infra_error import InfraError


def test_the_base_is_built_from_the_transport_our_address_and_the_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """DNS в пути показа не участвует: адрес собирается из транспорта, адреса и порта.

    Имя тут стоило бы показу отдельной точки отказа - ТВ ходит по IP и разрешать имена
    в сегменте телевизора некому.
    """
    monkeypatch.setattr(module, "our_address", lambda tv: "10.0.100.5")
    config = Config(tv="10.0.100.9", transport="http", hls_port=8080)
    assert module.hls_base(config) == "http://10.0.100.5:8080"


def test_the_configured_base_overrides_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    """Запасной выход: заданная в конфиге база перебивает собранную и не спрашивает маршрут."""

    def never(tv: str) -> str:  # pragma: no cover - до него не доходит
        raise AssertionError("маршрут спрашивать незачем: база задана")

    monkeypatch.setattr(module, "our_address", never)
    config = Config(tv="10.0.100.9", hls_base_url="https://кино.дома:9443/")
    assert module.hls_base(config) == "https://кино.дома:9443"


def test_without_a_route_to_the_receiver_the_base_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Маршрута нет - беда словами. Молча собранная база уводит показ в никуда."""
    monkeypatch.setattr(module, "our_address", lambda tv: "")
    with pytest.raises(InfraError, match="не вижу маршрута до ТВ"):
        module.hls_base(Config(tv="10.0.100.9"))
    with pytest.raises(InfraError, match="адрес не задан"):
        module.hls_base(Config())
