"""Сорванный круг пуст, как отказ, но несёт ошибку: сезоны читают его как «не знаю»."""

from __future__ import annotations

from torrcast.domain.infra_error import InfraError
from web.torn_circle import TornCircle


def test_a_torn_circle_is_empty_and_carries_its_error() -> None:
    error = InfraError("indexers did not answer")
    torn = TornCircle(error)
    assert torn == [] and not torn, "ждущие круга видят отказ и сеть до срока не переспрашивают"
    assert torn.error is error
