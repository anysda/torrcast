"""Признак приёмника: рукопожатие TLS, а не открытый порт и не быстрый SYN-ACK."""

from __future__ import annotations

import socket
import ssl
import threading
import time

import pytest

from torrcast.adapters.chromecast.scan.alive import CAST_PORT, PROBE_TIMEOUT, alive


@pytest.mark.machine
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
        assert not alive("127.0.0.1", port=port, timeout=0.5)
    finally:
        server.close()


@pytest.mark.machine
def test_a_tls_speaking_port_is_a_receiver(tls: tuple[str, str]) -> None:
    """А вот тот, кто рукопожатие довёл до конца, приёмником считается.

    Серт у приёмников самоподписанный, и доверять ему мы не обязаны: нужен факт «на том
    конце живой TLS», а не цепочка до корня - иначе ни один Chromecast проверку бы не
    прошёл.
    """
    cert, key = tls
    with _tls_server(cert, key) as port:
        assert alive("127.0.0.1", port=port, timeout=5.0)


@pytest.mark.machine
def test_a_dead_address_does_not_hold_the_search() -> None:
    """Адрес, на котором никого нет, обязан отваливаться по таймауту, а не висеть."""
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        free = int(sock.getsockname()[1])

    started = time.monotonic()
    assert not alive("127.0.0.1", port=free, timeout=0.5)
    assert time.monotonic() - started < 2.0


def test_the_port_and_the_patience_are_the_ones_the_walk_counts_on() -> None:
    """Порт управления и терпение на адрес: на них умножается длина подсети.

    8009 открыт даже в standby, поэтому по нему приёмник и виден; секунда терпения -
    это уже щедро для своей подсети, а множится она на 254 адреса.
    """
    assert CAST_PORT == 8009
    assert PROBE_TIMEOUT == 1.0


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
