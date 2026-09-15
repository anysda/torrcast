"""Зеркало :mod:`hass.facts_weather`: погоду приговору рассказывает общий клиент справки."""

from __future__ import annotations

import pytest

from hass.facts_weather import FactsWeather, _CalmWeather
from torrcast.runtime.facts_wiring import FACTS


class _Told:
    def troubled_since(self, moment: float) -> bool:
        return moment <= 5.0

    def calm_at(self) -> float:
        return 42.0


def test_the_weather_is_the_one_of_the_shared_client(monkeypatch: pytest.MonkeyPatch) -> None:
    """429 и отказы считает клиент Wikimedia; приговор читает их у него же."""
    monkeypatch.setattr(FACTS, "client", _Told())
    weather = FactsWeather()
    assert weather.troubled_since(1.0) and not weather.troubled_since(9.0)
    assert weather.calm_at() == 42.0


def test_a_client_without_a_count_is_always_calm(monkeypatch: pytest.MonkeyPatch) -> None:
    """Подделка клиента без счёта отказов не делает каждый пустой ответ неизвестным."""
    monkeypatch.setattr(FACTS, "client", object())
    assert not FactsWeather().troubled_since(0.0)
    assert not _CalmWeather().troubled_since(0.0)
    assert _CalmWeather().calm_at() < 0.0
