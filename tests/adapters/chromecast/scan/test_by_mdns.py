"""Слушание mDNS: три различимые причины пустого ответа вместо одного молчания."""

from __future__ import annotations

import sys

import pytest

from torrcast.adapters.chromecast.scan.by_mdns import MDNS_TIMEOUT, by_mdns


class _FakeZeroconf:
    def __init__(self, *_args: object, **_kwargs: object) -> None:
        pass

    def close(self) -> None:
        pass


class _FakeBrowser:
    """Браузер mDNS без сети: ``devices`` пуст, как в эфире без приёмников."""

    def __init__(self, *_args: object) -> None:
        self.devices: dict[str, object] = {}

    def start_discovery(self) -> None:
        pass

    def stop_discovery(self) -> None:
        pass


def _quiet_ether(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слушание mDNS без живой сети: сокет поднялся, эфир молчит."""
    import pychromecast.discovery
    import zeroconf

    monkeypatch.setattr(zeroconf, "Zeroconf", _FakeZeroconf)
    monkeypatch.setattr(pychromecast.discovery, "CastBrowser", _FakeBrowser)


def test_mdns_without_the_module_names_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Системный python без zeroconf - та самая ложная тревога: причина обязана звучать."""
    monkeypatch.setitem(sys.modules, "zeroconf", None)  # import zeroconf упадёт

    heard = by_mdns(timeout=0.01)

    assert heard.devices == []
    assert heard.reason == "module"
    assert "zeroconf" in heard.note


def test_mdns_without_multicast_names_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Сеть не дала поднять мультикаст - это другая причина, и она с текстом ошибки."""
    import zeroconf

    def refuse(*_args: object, **_kwargs: object) -> object:
        raise OSError("мультикаста нет")

    monkeypatch.setattr(zeroconf, "Zeroconf", refuse)

    heard = by_mdns(timeout=0.01)

    assert heard.devices == []
    assert heard.reason == "network"
    assert "мультикаста нет" in heard.note


def test_mdns_silence_is_named_too(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слушали честно и никого не услышали - третья причина, не «ошибка сети»."""
    _quiet_ether(monkeypatch)

    heard = by_mdns(timeout=0.01)

    assert heard.devices == []
    assert heard.reason == "silence"
    assert "никто не отозвался" in heard.note


def test_mdns_broken_listening_names_the_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """Слушание оборвалось посередине - это «network», и текст обрыва виден."""
    _quiet_ether(monkeypatch)

    def blow_up(self: _FakeBrowser) -> None:
        raise RuntimeError("сокет умер")

    monkeypatch.setattr(_FakeBrowser, "start_discovery", blow_up)

    heard = by_mdns(timeout=0.01)

    assert heard.devices == []
    assert heard.reason == "network"
    assert "сокет умер" in heard.note


def test_a_heard_receiver_comes_with_its_human_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ради имён mDNS и слушают: обход подсетей их не знает вовсе."""
    _quiet_ether(monkeypatch)

    class _Info:
        host = "10.0.0.50"
        friendly_name = "Samsung Q70D"
        model_name = "SAMSUNG"
        manufacturer = "Samsung"

    class _LoudBrowser(_FakeBrowser):
        def __init__(self, *args: object) -> None:
            super().__init__(*args)
            self.devices = {"uuid": _Info()}

    import pychromecast.discovery

    monkeypatch.setattr(pychromecast.discovery, "CastBrowser", _LoudBrowser)

    heard = by_mdns(timeout=0.01)

    assert [device.name for device in heard.devices] == ["Samsung Q70D"]
    assert heard.devices[0].how == "mdns"
    assert heard.devices[0].maker == "Samsung"
    assert heard.reason == ""


def test_the_listening_window_is_short_because_the_answer_comes_at_once() -> None:
    """Приёмник отвечает на первый же запрос, дальше идёт тишина - ждать дольше незачем.

    Окно стоит в бюджете старта целиком: поиск идёт до первого кадра.
    """
    assert MDNS_TIMEOUT == 4.0
