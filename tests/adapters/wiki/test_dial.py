"""Дозвон источника картинок не ждёт повтора SYN ядром (:mod:`torrcast.adapters.wiki.dial`).

Потерю SYN тут делает само ядро, без сети и без прав: слушающий сокет с полной очередью
приёма молча роняет новый SYN, и обычный дозвон повторяет его только через секунду. Очередь
освобождается почти сразу, поэтому опоздать может лишь тот, кто ждёт повтора ядра.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Iterator
from typing import Any

import pytest

from torrcast.adapters.wiki import dial as dial_module
from torrcast.adapters.wiki.dial import HEDGE, dial
from torrcast.adapters.wiki.http_json_client import _IPv4Connection

#: Когда ядро повторяет потерянный SYN впервые, секунды.
_KERNEL_RETRY = 1.0
#: Когда очередь приёма освобождается после первого SYN.
_FREED_AT = 0.05
#: Сколько сокетов один запрос вправе открыть на молчащий адрес: шесть картин ряда звонят
#: разом, и без потолка их попытки за срок 4 с шли бы десятками.
_SOCKETS_AT_MOST = 8


@pytest.fixture
def full_queue() -> Iterator[int]:
    """Порт, у которого очередь приёма полна; через :data:`_FREED_AT` с её разбирают."""
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(("127.0.0.1", 0))
    server.listen(0)
    port = server.getsockname()[1]
    first = socket.create_connection(("127.0.0.1", port), 1.0)  # занимает единственное место

    def free() -> None:
        time.sleep(_FREED_AT)
        server.accept()[0].close()

    taker = threading.Thread(target=free, daemon=True, name="free-queue")
    taker.start()
    try:
        yield port
    finally:
        taker.join(5.0)
        first.close()
        server.close()


class _Plain:
    """TLS тут не проверяется: сокет дозвона отдаётся как есть."""

    def wrap_socket(self, raw: socket.socket, **_: str) -> socket.socket:
        return raw


@pytest.mark.machine
def test_a_lost_syn_is_redialled_before_the_kernel_retries_it(
    full_queue: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Соединение источника встаёт со второй попытки, а не через секунду ядра.

    Дом терял 10-60% первых SYN к IMDb и Википедии, и запрос подсказчика упирался в свой
    срок 4 с при ответе сервера за десятые доли секунды (замер 02-10-2026).
    """
    monkeypatch.setattr(_IPv4Connection, "context", _Plain())
    connection = _IPv4Connection(f"127.0.0.1:{full_queue}", 5.0, lambda host, timeout: host)
    began = time.monotonic()
    connection.connect()
    took = time.monotonic() - began
    try:
        assert took < _KERNEL_RETRY - 0.2, f"дозвон ждал повтора ядра: {took:.2f} с"
        assert took >= HEDGE - 0.05, f"первая попытка не терялась: {took:.2f} с"
    finally:
        connection.close()


@pytest.mark.machine
def test_a_refusal_is_an_answer_and_not_a_redial() -> None:
    """Сервер ответил отказом - это ответ: он отдаётся сразу, без запасных попыток до срока."""
    dead = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    dead.bind(("127.0.0.1", 0))
    port = dead.getsockname()[1]
    dead.close()
    began = time.monotonic()
    with pytest.raises(ConnectionRefusedError):
        dial("127.0.0.1", port, 5.0)
    assert time.monotonic() - began < HEDGE


@pytest.mark.machine
def test_a_silent_address_times_out_at_its_own_deadline(full_queue: int) -> None:
    """Не ответила ни одна попытка - отказ по сроку, как у ядра, и не позже срока."""
    blocker: list[Any] = []
    try:
        time.sleep(_FREED_AT * 2)  # место освободилось - займём его снова и навсегда
        blocker.append(socket.create_connection(("127.0.0.1", full_queue), 1.0))
        began = time.monotonic()
        with pytest.raises(TimeoutError):
            dial("127.0.0.1", full_queue, 0.8)
        assert time.monotonic() - began < 0.8 + 0.2
    finally:
        for one in blocker:
            one.close()


@pytest.mark.machine
def test_a_silent_address_opens_a_bounded_number_of_sockets(
    full_queue: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Молчащий адрес получает не больше восьми попыток за запрос, сколько бы ни длился срок."""
    opened: list[int] = []
    attempt = dial_module._attempt

    def counted(address: str, port: int, chooser: Any) -> socket.socket:
        opened.append(port)
        return attempt(address, port, chooser)

    monkeypatch.setattr(dial_module, "_attempt", counted)
    blocker: list[Any] = []
    try:
        time.sleep(_FREED_AT * 2)
        blocker.append(socket.create_connection(("127.0.0.1", full_queue), 1.0))
        with pytest.raises(TimeoutError):
            dial("127.0.0.1", full_queue, HEDGE * (_SOCKETS_AT_MOST + 4))
        assert len(opened) <= _SOCKETS_AT_MOST, f"на молчащий адрес открыто {len(opened)} сокетов"
    finally:
        for one in blocker:
            one.close()
