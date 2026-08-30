"""Один и тот же отказ, снятый живым трактом и сухим: лента обязана выйти одна.

🔴 Сухой прогон затем и нужен, чтобы по нему судить о живом. Лента, у которой поля не те
же, судить не даёт: замер TC-880 испортила ровно эта разница - ноль подъёмов приёмника в
сухом прогоне значил не «продукт передумал поднимать», а «процесс упал раньше, чем успел».
Живой тракт три исхода развёл (TC-903), сухой - нет, и сличать их было нечем.

Зеркало тут не у модуля, а у стыка двух трактов: предмет проверки - совпадение их лент.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

from tests.adapters.chromecast.cast.wired import Device, Quiet
from tests.conftest import FakeProc
from tests.fakes.clock import FakeClock
from tests.usecases.revive_playback.world import FakeSupply, feed_with_segments
from torrcast.adapters.chromecast.mock.hls_fetch import CORS_HEADER
from torrcast.adapters.chromecast.mock.mock_receiver import MockReceiver
from torrcast.domain.position import Position
from torrcast.domain.profile import ANDROID_TV
from torrcast.ports.journal.silent import Silent
from torrcast.ports.journal.slot import install
from torrcast.ports.receiver import Receiver
from torrcast.ports.stream_source import StreamSource
from torrcast.usecases.revive_playback._resurrect import _resurrect
from torrcast.usecases.revive_playback._revival_state import _RevivalState

URL = "http://127.0.0.1:9/hls/index.m3u8"
#: Отказ, который оба тракта умеют изобразить дословно одинаково: приёмника нет в сети.
GONE = OSError("приёмника нет в сети")


class _Tape(Silent):
    """Лента, запоминающая запись подъёма целиком: сличают именно её поля."""

    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    def revive(self, pos: float, tries: int, waited: float, ok: bool, why: str = "") -> None:
        self.rows.append({"pos": pos, "tries": tries, "waited": waited, "ok": ok, "why": why})


class _Paper:
    """Раздача на бумаге: отдаёт пустой манифест либо падает названной аварией."""

    status_code = 200
    text = ""

    def __init__(self) -> None:
        self.headers = {CORS_HEADER: "*"}
        self.breaks: Exception | None = None

    def get(self, url: str, timeout: float = 0.0) -> _Paper:
        if self.breaks is not None:
            raise self.breaks
        return self

    def raise_for_status(self) -> None:
        return None


class _Silent:
    """Поток, которого нет: фоновых читателей тут не заводится."""

    def start(self) -> None:
        pass

    def join(self, timeout: float | None = None) -> None:
        pass


def test_one_and_the_same_refusal_writes_one_and_the_same_row_in_both_tracts(
    tmp_path: Path,
) -> None:
    """🔴 Сценарий один - «приёмника нет в сети», - и запись ленты обязана выйти одна.

    Сличается запись целиком, а не одно поле: развести одно и не развести другое значит
    сделать ленты несовпадающими по-новому, и это труднее заметить, чем честное отсутствие.
    """
    live = _row(Quiet(breaks=True), tmp_path)
    dry = _row(_dry_that_crashed(), tmp_path)

    assert live.keys() == dry.keys(), "поля записи обязаны совпасть по именам"
    assert live == dry, f"один отказ - одна запись; живой {live}, сухой {dry}"
    assert live["why"] == "упал: приёмника нет в сети"


def test_both_tracts_name_the_outcomes_by_the_same_three_words(tmp_path: Path) -> None:
    """🔴 Словарь исходов у трактов один: «нельзя», «упал», «не взял».

    Меряется РАЗЛИЧИЕ, а не наличие: словарь из одного слова прошёл бы проверку «поле
    заполнено» и оставил бы ленту ровно такой же нечитаемой, какой она была без поля.
    """
    live = [_row(rcv, tmp_path)["why"] for rcv in _live_refusals()]
    dry = [_row(rcv, tmp_path)["why"] for rcv in _dry_refusals()]

    assert len(set(live)) == 3, f"живой тракт обязан различать три исхода: {live}"
    assert len(set(dry)) == 3, f"сухой тракт обязан различать три исхода: {dry}"
    assert _words(live) == _words(dry), f"словари исходов разошлись: {live} против {dry}"


def _words(said: list[object]) -> list[str]:
    """Слово исхода из названной причины: по нему замер и считает подъёмы."""
    return [str(word).split(":")[0] for word in said]


def _row(receiver: Receiver, tmp_path: Path) -> dict[str, object]:
    """Запись ``play/revive``, которую оставил в ленте один круг подъёма."""
    tape = _Tape()
    install(tape)
    try:
        _resurrect(
            _RevivalState(
                clock=FakeClock(now=1000.0),
                supply=cast(StreamSource, FakeSupply()),
                drop=0.0,
            ),
            receiver,
            feed_with_segments(tmp_path),
            None,
            120.0,
        )
    finally:
        install(Silent())
    (row,) = tape.rows
    assert row["ok"] is False, "все три исхода - это отсутствие картинки, и различие не в нём"
    return row


def _live_refusals() -> list[Receiver]:
    """Три исхода живого тракта: чужой показ, легшее соединение, ушедший LOAD без кадра."""
    return [
        cast(Receiver, Quiet(device=Device(app="чужое"))),
        cast(Receiver, Quiet(breaks=True)),
        cast(Receiver, Quiet(settles=False)),
    ]


def _dry_refusals() -> list[Receiver]:
    """Те же три исхода сухого тракта - теми же словами, но своими причинами."""
    return [
        cast(Receiver, _dry_that_is_forbidden()),
        cast(Receiver, _dry_that_crashed()),
        cast(Receiver, _dry_that_did_not_take_it()),
    ]


def _dry(clock: FakeClock | None = None, **rest: Any) -> tuple[MockReceiver, _Paper]:
    """Сухой приёмник на бумажной раздаче, уже заведённый на показ."""
    mock = MockReceiver(
        clock=clock or FakeClock(1000.0),
        spawn=lambda *args, **kw: FakeProc(),
        thread=lambda **kw: _Silent(),
        **rest,
    )
    paper = _Paper()
    mock.fetch.session = lambda ca: paper
    mock.play(URL, at=120.0)
    return mock, paper


def _dry_that_is_forbidden() -> MockReceiver:
    """Соваться нельзя: приёмник помнит 404 и LOAD не берёт вовсе."""
    clock = FakeClock(1000.0)
    mock, _ = _dry(clock, profile=ANDROID_TV)
    mock.fetch.sulk_until = clock.monotonic() + 150.0
    return mock


def _dry_that_crashed() -> MockReceiver:
    """Упало соединение: тот же ``OSError``, что и у живого приёмника без сети."""
    mock, paper = _dry()
    paper.breaks = GONE
    return mock


def _dry_that_did_not_take_it() -> MockReceiver:
    """LOAD ушёл, а картинки не было: декодер лёг, не начав показ."""
    mock, _ = _dry()
    mock.decoder.pos = Position(120.0, 7200.0, False)
    return mock
