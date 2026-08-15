"""UDP-щуп считает ответом только ответ на собственный connect."""

from __future__ import annotations

import importlib.util
import socket
import struct
import sys
from pathlib import Path

import pytest

SPEC = importlib.util.spec_from_file_location(
    "trackerprobe", Path(__file__).resolve().parent.parent / "scripts/trackerprobe.py"
)
assert SPEC is not None and SPEC.loader is not None
tracker = importlib.util.module_from_spec(SPEC)
sys.modules["trackerprobe"] = tracker
SPEC.loader.exec_module(tracker)


def test_tracker_probe_checks_the_transaction_id(monkeypatch: pytest.MonkeyPatch) -> None:
    class Socket:
        def __enter__(self) -> Socket:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

        def settimeout(self, _timeout: float) -> None:
            return None

        def sendto(self, packet: bytes, _peer: object) -> None:
            self.packet = packet

        def recvfrom(self, _size: int) -> tuple[bytes, object]:
            _protocol, _action, transaction = struct.unpack("!QII", self.packet)
            return struct.pack("!IIQ", 0, transaction, 1), ("tracker", 1)

    monkeypatch.setattr(tracker.socket, "gethostbyname", lambda _host: "127.0.0.1")
    monkeypatch.setattr(tracker.socket, "socket", lambda *_args: Socket())
    assert tracker.connect("udp://tracker:80/announce", 0.1)["ok"] is True


class _Answer:
    """Сокет, отвечающий заготовленными байтами - хоть мусором, хоть обрубком."""

    def __init__(self, answer: bytes) -> None:
        self._answer = answer

    def __enter__(self) -> _Answer:
        return self

    def __exit__(self, *_args: object) -> None:
        return None

    def settimeout(self, _timeout: float) -> None:
        return None

    def sendto(self, _packet: bytes, _peer: object) -> None:
        return None

    def recvfrom(self, _size: int) -> tuple[bytes, object]:
        return self._answer, ("tracker", 1)


@pytest.mark.parametrize(
    ("answer", "why"),
    [
        (b"", "трекер промолчал телом - ответа нет"),
        (b"\x00\x01", "обрубок короче восьми байт роняет struct.unpack"),
        (b"garbage!" * 4, "мусор той же длины разбирается, но это не наш connect"),
    ],
)
def test_tracker_probe_calls_a_junk_answer_a_refusal(
    monkeypatch: pytest.MonkeyPatch, answer: bytes, why: str
) -> None:
    """🔴 Мусорный ответ трекера - это ``ok: false``, а не падение всего щупа.

    ``struct.error`` не наследник ``OSError``, поэтому обрубок короче восьми байт уходил
    мимо охраны и уносил с собой опрос ВСЕХ остальных трекеров: один больной источник
    обязан сужать список ответивших, а не ломать замер.
    """
    monkeypatch.setattr(tracker.socket, "gethostbyname", lambda _host: "127.0.0.1")
    monkeypatch.setattr(tracker.socket, "socket", lambda *_args: _Answer(answer))
    row = tracker.connect("udp://tracker:80/announce", 0.1)

    assert row["ok"] is False, why
    assert row["tracker"] == "tracker" and row["port"] == 80


def test_tracker_probe_survives_a_name_that_no_longer_resolves(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Имя трекера перестало разрешаться - это отказ источника, а не отказ щупа.

    ``socket.gaierror`` хоть и ``OSError``, но резолв стоял ВНЕ охраны, и мёртвое имя
    роняло весь опрос до первой же строки вывода.
    """

    def gone(_host: str) -> str:
        raise socket.gaierror(-2, "Name or service not known")

    monkeypatch.setattr(tracker.socket, "gethostbyname", gone)
    assert tracker.connect("udp://tracker:80/announce", 0.1)["ok"] is False


def test_tracker_probe_survives_an_address_without_a_port(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Адрес без порта - тоже отказ строкой, а не ``ValueError`` посреди опроса."""
    monkeypatch.setattr(tracker.socket, "gethostbyname", lambda _host: "127.0.0.1")
    row = tracker.connect("udp://tracker/announce", 0.1)

    assert row["ok"] is False and row["port"] == 0
