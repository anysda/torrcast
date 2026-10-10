"""Хвост паспорта, который читается дольше бюджета: время головы - его, позднее - на полку."""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Any

import pytest

import torrcast.adapters.stream_probe.probe as probe_module
from torrcast.adapters.stream_probe.media_shelf import _media_cache
from torrcast.adapters.stream_probe.probe import TAIL_LIFE, Runner, probe

if TYPE_CHECKING:
    from pathlib import Path

_ANSWER = json.dumps({"format": {"duration": "3600.0"}, "streams": [
    {"index": 0, "codec_name": "h264", "codec_type": "video", "width": 1920, "height": 1080},
    {"index": 1, "codec_name": "ac3", "codec_type": "audio", "channels": 6},
]})  # fmt: skip

#: Хвост файла, чья картинка кончается за 600 с до конца контейнера (файл дочитан окном).
_SHORT = "video,2999.96,0.04\naudio,3000.5,0.032\n"


def _slow(head: float, tail: threading.Event, timeouts: list[float]) -> Runner:
    """Голова отвечает через ``head`` секунд, хвост - когда поднят ``tail``."""

    def _run(command: list[str], timeout: float, alive: Any) -> str:
        if "-seekable" in command:
            time.sleep(head)
            return _ANSWER
        timeouts.append(timeout)
        tail.wait(5.0)
        return _SHORT

    return _run


@pytest.mark.machine  # настоящие потоки и время: хвост медленнее бюджета
def test_a_tail_slower_than_its_budget_still_counts_while_the_head_is_read(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """🔴 Стенд: холодная голова «Отчаянных домохозяек» читалась 26.8 с, а хвост рядом с ней
    обрывали на 8 с - и сетка снова ждала кусков за последним кадром. Хвост живёт, пока
    читается голова, и бюджет считается от её ответа.

    Отрицательная проба: бюджет от начала (``min(timeout, TAIL_BUDGET)`` в запуск хвоста).
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(probe_module, "TAIL_BUDGET", 0.2)
    ready, timeouts = threading.Event(), list[float]()
    threading.Timer(0.4, ready.set).start()  # хвост дольше бюджета, но раньше головы
    media = probe("http://torr/stream/hash-1/2", run=_slow(0.6, ready, timeouts))
    assert media.duration == pytest.approx(3000.0)
    assert timeouts == [TAIL_LIFE], "хвосту дано время головы, а не бюджет от начала"


@pytest.mark.machine
def test_a_tail_that_lands_after_the_answer_reaches_the_shelf_for_the_next_show(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Опоздавший хвост не задерживает показ, но и не теряется: возврат к месту обрыва
    повторным ``cast`` уже знает конец картинки.

    Отрицательная проба: не дочитывать хвост в фоне - второй щуп идёт в ffprobe снова.
    """
    monkeypatch.setenv("TORRCAST_STATE", str(tmp_path / "state.json"))
    monkeypatch.setattr(probe_module, "TAIL_BUDGET", 0.05)
    late, timeouts = threading.Event(), list[float]()
    first = probe("http://torr/stream/hash-1/2", run=_slow(0.0, late, timeouts))
    assert first.duration == 3600.0, "не дождались хвоста - длительность по контейнеру"
    late.set()
    shelf = _media_cache("http://torr/stream/hash-1/2")
    deadline = time.monotonic() + 5.0
    while not shelf.exists() and time.monotonic() < deadline:
        time.sleep(0.01)

    def boom(*_a: object) -> str:
        raise AssertionError("паспорт обязан прийти с полки")

    assert probe("http://torr/stream/hash-1/2", run=boom).duration == pytest.approx(3000.0)
