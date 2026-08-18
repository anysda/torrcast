"""Поиск целиком: два способа разом, слияние по адресу и честные строки о пропущенном."""

from __future__ import annotations

from torrcast.adapters.chromecast.scan.device import Device
from torrcast.adapters.chromecast.scan.find import find
from torrcast.adapters.chromecast.scan.mdns import Mdns
from torrcast.adapters.chromecast.scan.net import Net


def test_mdns_and_the_scan_merge_by_address_and_the_name_wins() -> None:
    """Одно устройство, найденное обоими способами, - один пункт меню, и он с именем.

    Иначе телевизор попадал бы в список дважды: строкой «Samsung Q70D» от mDNS и
    безымянной строкой от обхода порта. Имя от mDNS - то самое, что человек видит в
    настройках телевизора, поэтому оно и выигрывает.
    """
    asked: list[str] = []

    def name_of(address: str) -> Device:
        asked.append(address)
        return Device(address, model="Chromecast", how="скан")

    found = find(
        nets=lambda: [Net("eth0", "10.0.0.7", "255.255.255.0")],
        listen=lambda _timeout: Mdns([Device("10.0.0.50", name="Samsung Q70D", how="mdns")]),
        walk=lambda *_a: ["10.0.0.50", "10.0.0.60", "10.0.0.9"],
        name=name_of,
    )

    assert [device.address for device in found.devices] == ["10.0.0.9", "10.0.0.50", "10.0.0.60"]
    assert found.devices[1].name == "Samsung Q70D", "имя от mDNS перебивает обход"
    assert found.devices[2].title == "Chromecast"
    assert sorted(asked) == ["10.0.0.60", "10.0.0.9"], "имя у известного по mDNS не переспрашиваем"


def test_find_says_why_mdns_is_silent() -> None:
    """Пустой mDNS - не молчок: причина приезжает в notes и печатается перед меню.

    Именно отсутствие этой строки однажды родило ложную тревогу: «приёмник молчит» было
    не отличить от «в этом python нет zeroconf».
    """
    silent = Mdns(reason="module", note="нет zeroconf")

    found = find(
        nets=lambda: [Net("eth0", "10.0.0.7", "255.255.255.0")],
        listen=lambda _timeout: silent,
        walk=lambda *_a: ["10.0.0.50"],
        name=lambda address: Device(address, how="скан"),
    )

    assert "нет zeroconf" in found.notes


def test_a_subnet_too_wide_to_walk_is_reported_before_the_menu() -> None:
    """Про необойденное сказано в том же ответе, что и про найденное."""
    found = find(
        nets=lambda: [Net("br0", "172.30.0.1", "255.255.0.0")],
        listen=lambda _timeout: Mdns(),
        walk=lambda *_a: [],
    )

    assert found.devices == []
    assert any("172.30.0.0/16" in note for note in found.notes)


def test_our_own_addresses_never_reach_the_walk() -> None:
    """Свой адрес в обход не уезжает: сами себе мы не телевизор."""
    walked: list[list[str]] = []

    def remember(addresses: list[str], *_a: object) -> list[str]:
        walked.append(addresses)
        return []

    find(
        nets=lambda: [Net("eth0", "10.0.0.7", "255.255.255.0")],
        listen=lambda _timeout: Mdns(),
        walk=remember,
    )

    assert walked and "10.0.0.7" not in walked[0]
    assert len(walked[0]) == 253
