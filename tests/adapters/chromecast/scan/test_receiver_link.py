"""Зеркало :mod:`torrcast.adapters.chromecast.scan.receiver_link`."""

from __future__ import annotations

from typing import Any

import pytest
import requests

from torrcast.adapters.chromecast.scan.receiver_link import SETUP_PORT, receiver_link


class _Reply:
    def __init__(self, payload: object) -> None:
        self.payload = payload

    def json(self) -> object:
        return self.payload


def _answer(monkeypatch: pytest.MonkeyPatch, payload: object) -> list[str]:
    asked: list[str] = []

    def get(url: str, timeout: float = 0.0, **_rest: Any) -> _Reply:
        asked.append(url)
        return _Reply(payload)

    monkeypatch.setattr(requests, "get", get)
    return asked


def test_the_passport_is_read_by_one_plain_request(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ни каста, ни сендера: обычный HTTP к странице сведений, приёмник им не будится."""
    asked = _answer(monkeypatch, {"uptime": 98765.4, "ethernet_connected": False})

    assert receiver_link("10.0.0.50", 2.0) == (98765.4, False)
    assert asked == [f"http://10.0.0.50:{SETUP_PORT}/setup/eureka_info"]


def test_a_wired_receiver_is_told_apart_from_a_wireless_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answer(monkeypatch, {"uptime": 10.0, "ethernet_connected": True})
    assert receiver_link("10.0.0.50", 2.0) == (10.0, True)


def test_fields_the_device_never_named_come_back_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """Чего в паспорте нет, то и не выдумываем: ноль секунд и «не сказал»."""
    _answer(monkeypatch, {"ssid": "дом"})
    assert receiver_link("10.0.0.50", 2.0) == (0.0, None)


def test_a_boolean_uptime_is_not_taken_for_a_number(monkeypatch: pytest.MonkeyPatch) -> None:
    """``True`` в питоне - это единица, и без разбора она стала бы аптаймом в секунду."""
    _answer(monkeypatch, {"uptime": True})
    assert receiver_link("10.0.0.50", 2.0) == (0.0, None)


def test_a_page_that_is_not_a_passport_is_not_read_at_all(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _answer(monkeypatch, ["не паспорт"])
    assert receiver_link("10.0.0.50", 2.0) == (0.0, None)


def test_a_silent_receiver_is_not_an_exception(monkeypatch: pytest.MonkeyPatch) -> None:
    """Приёмник выключен - проба отвечает значением: самопроверка на этом не падает."""

    def refuse(url: str, timeout: float = 0.0, **_rest: Any) -> _Reply:
        raise requests.ConnectionError("Connection refused")

    monkeypatch.setattr(requests, "get", refuse)
    assert receiver_link("10.0.0.50", 2.0) == (0.0, None)
