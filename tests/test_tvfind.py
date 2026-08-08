"""Поиск приёмников в сети: чем приёмник отличается от открытого порта, какие подсети
мы вообще смотрим и как склеивается найденное двумя способами.

Живой сети тут нет ни в одном тесте: интерфейсы, mDNS и обход подменяются, а
«рукопожатие» проверяется на настоящих, но локальных сокетах - иначе проверять нечего.
"""

from __future__ import annotations

import socket
import ssl
import threading
import time

import pytest

from torrcast import scan
from torrcast.scan import Device, Net


def test_an_open_port_is_not_a_receiver_yet() -> None:
    """Порт открыт, а рукопожатия нет - это не телевизор.

    Так выглядит сетевой посредник: прокси и транзитный VPN отвечают SYN-ACK за любой
    адрес любой подсети. Проверка одним коннектом объявила бы приёмником каждый адрес
    подряд, и в меню приехали бы «254 телевизора». Признак поэтому - TLS-рукопожатие:
    ServerHello молчащей заглушке взять неоткуда.
    """
    server = socket.socket()
    server.bind(("127.0.0.1", 0))
    server.listen(1)  # соединение примет ядро, а говорить с ним никто не будет
    port = int(server.getsockname()[1])
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()  # порт правда открыт
        assert not scan.alive("127.0.0.1", port=port, timeout=0.5)
    finally:
        server.close()


def test_a_tls_speaking_port_is_a_receiver(tls: tuple[str, str]) -> None:
    """А вот тот, кто рукопожатие довёл до конца, приёмником считается.

    Серт у приёмников самоподписанный, и доверять ему мы не обязаны: нужен факт «на том
    конце живой TLS», а не цепочка до корня - иначе ни один Chromecast проверку бы не
    прошёл.
    """
    cert, key = tls
    with _tls_server(cert, key) as port:
        assert scan.alive("127.0.0.1", port=port, timeout=5.0)


def test_a_dead_address_does_not_hold_the_search() -> None:
    """Адрес, на котором никого нет, обязан отваливаться по таймауту, а не висеть."""
    started = time.monotonic()
    assert not scan.alive("127.0.0.1", port=_free_port(), timeout=0.5)
    assert time.monotonic() - started < 2.0


def test_huge_subnets_are_skipped_out_loud() -> None:
    """Подсети шире потолка не обходим, но и не умалчиваем.

    ``/16`` - это 65534 адреса, то есть минуты вместо секунд. Молча уйти в такой обход
    хуже, чем сказать вслух: «эту не смотрю, задай адрес руками».
    """
    good, huge = scan.subnets(
        [
            Net("lo", "127.0.0.1", "255.0.0.0"),
            Net("eth0", "10.0.0.7", "255.255.255.0"),
            Net("eth1", "10.5.0.7", "255.255.0.0"),
            Net("wg0", "10.9.0.2", "255.255.255.255"),
            Net("eth2", "10.0.0.9", "255.255.255.0"),  # та же подсеть второй ногой
            Net("br0", "172.30.0.1", "255.255.0.0"),
        ]
    )
    assert good == ["10.0.0.0/24"], "петля, точка-точка и дубль подсети отсеяны"
    assert huge == ["10.5.0.0/16", "172.30.0.0/16"]
    # Про все широкие подсети - ОДНА строка: на хосте с docker'ом их сразу три, и три
    # одинаковых абзаца перед меню прячут сам список приёмников.
    said = scan.skipped(huge)
    assert said.count("cast --tv <ip>") == 1
    assert "10.5.0.0/16" in said and "172.30.0.0/16" in said
    assert scan.skipped([]) == ""


def test_our_own_addresses_are_not_scanned() -> None:
    """Сами себе мы не телевизор: свой адрес из обхода вычёркивается."""
    addresses = scan.hosts(["10.0.0.0/24"], {"10.0.0.7"})
    assert len(addresses) == 253
    assert "10.0.0.7" not in addresses
    assert addresses[0] == "10.0.0.1" and addresses[-1] == "10.0.0.254"


def test_mdns_and_the_scan_merge_by_address_and_the_name_wins(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Одно устройство, найденное обоими способами, - один пункт меню, и он с именем.

    Иначе телевизор попадал бы в список дважды: строкой «Samsung Q70D» от mDNS и
    безымянной строкой от обхода порта. Имя от mDNS - то самое, что человек видит в
    настройках телевизора, поэтому оно и выигрывает.
    """
    asked: list[str] = []

    def name_of(address: str) -> Device:
        asked.append(address)
        return Device(address, model="Chromecast", how="скан")

    monkeypatch.setattr(scan, "interfaces", lambda: [Net("eth0", "10.0.0.7", "255.255.255.0")])
    monkeypatch.setattr(
        scan, "by_mdns", lambda _timeout: [Device("10.0.0.50", name="Samsung Q70D", how="mdns")]
    )
    monkeypatch.setattr(scan, "by_scan", lambda *_a, **_k: ["10.0.0.50", "10.0.0.60", "10.0.0.9"])
    monkeypatch.setattr(scan, "named", name_of)

    found = scan.find()

    assert [device.address for device in found.devices] == ["10.0.0.9", "10.0.0.50", "10.0.0.60"]
    assert found.devices[1].name == "Samsung Q70D", "имя от mDNS перебивает обход"
    assert found.devices[2].title == "Chromecast"
    assert sorted(asked) == ["10.0.0.60", "10.0.0.9"], "имя у известного по mDNS не переспрашиваем"


def test_a_nameless_receiver_still_gets_a_line() -> None:
    """Не представился - всё равно пункт меню: адрес у него есть, и человек его узнает."""
    assert Device("10.0.0.50").title == "приёмник"
    assert Device("10.0.0.50", model="Chromecast").title == "Chromecast"


def _free_port() -> int:
    """Номер порта, на котором сейчас никто не слушает."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class _tls_server:  # noqa: N801 - контекст-менеджер, а не тип данных
    """Локальный TLS-сокет на одно соединение: изображает приёмник на порту 8009."""

    def __init__(self, cert: str, key: str) -> None:
        self.context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        self.context.load_cert_chain(cert, key)
        self.sock = socket.socket()
        self.thread: threading.Thread | None = None

    def __enter__(self) -> int:
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(1)
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()
        return int(self.sock.getsockname()[1])

    def __exit__(self, *_exc: object) -> None:
        self.sock.close()
        if self.thread is not None:
            self.thread.join(timeout=5)

    def _serve(self) -> None:
        try:
            raw, _peer = self.sock.accept()
        except OSError:
            return
        try:
            with self.context.wrap_socket(raw, server_side=True):
                pass
        except (OSError, ssl.SSLError):
            pass
        finally:
            raw.close()
