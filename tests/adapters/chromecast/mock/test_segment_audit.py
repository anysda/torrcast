"""Зеркало :mod:`torrcast.adapters.chromecast.mock.segment_audit`."""

from __future__ import annotations

import threading
from typing import Final

import requests

from tests.fakes.clock import FakeClock
from torrcast.adapters.chromecast.mock.hls_fetch import CORS_HEADER, HlsFetch
from torrcast.adapters.chromecast.mock.segment_audit import SegmentAudit
from torrcast.domain.reception_report import ReceptionReport

URL = "http://127.0.0.1:9/hls/index.m3u8"
#: Декодер далеко впереди: сверка его не ждёт и идёт по манифесту подряд.
AHEAD: Final = 1e6


def _manifest(names: list[str], span: float = 10.0) -> str:
    lines = ["#EXTM3U", "#EXT-X-PLAYLIST-TYPE:VOD"]
    for name in names:
        lines += [f"#EXTINF:{span:.6f},", name]
    return "\n".join([*lines, "#EXT-X-ENDLIST", ""])


class _Served:
    """Ответ раздачи на бумаге: CORS на месте, размер назван, кода ошибки нет."""

    status_code = 200

    def __init__(self, text: str = "", size: int = 1024, cors: bool = True) -> None:
        self.text = text
        self.headers = {"Content-Length": str(size)}
        if cors:
            self.headers[CORS_HEADER] = "*"

    def raise_for_status(self) -> None:
        return None


class _Answers:
    """Раздача на бумаге: манифест на GET, размер на HEAD, и список всего, что спросили."""

    def __init__(self, body: str, size: int = 1024, cors: bool = True) -> None:
        self.body, self.size, self.cors = body, size, cors
        self.asked: list[str] = []

    def get(self, url: str, timeout: float = 0.0) -> _Served:
        self.asked.append(f"GET {url}")
        return _Served(self.body)

    def head(self, url: str, timeout: float = 0.0) -> _Served:
        self.asked.append(f"HEAD {url}")
        return _Served(size=self.size, cors=self.cors)


def _audit(answers: _Answers) -> tuple[SegmentAudit, ReceptionReport]:
    report = ReceptionReport()
    fetch = HlsFetch("", FakeClock())
    fetch.session = lambda ca: answers
    return SegmentAudit(report, fetch), report


def _heads(answers: _Answers) -> list[str]:
    return [name.rsplit("/", 1)[1] for name in answers.asked if name.startswith("HEAD")]


def test_the_pieces_left_behind_the_entry_point_are_never_asked_for() -> None:
    """Кусок, который КОНЧАЕТСЯ на месте захода, приёмнику не нужен: он весь позади.

    Один лишний ``HEAD`` на нулевой кусок уводит упаковку на голову фильма, и в замере
    продолжения появляется заход, которого показ не делал.
    """
    answers = _Answers(_manifest([f"v{slot}.ts" for slot in range(6)]))
    audit, report = _audit(answers)

    audit.run(URL, 10.0, lambda: AHEAD, threading.Event())

    assert _heads(answers) == [f"v{slot}.ts" for slot in (1, 2, 3, 4, 5)]
    assert report.gaps == 0, "начало сверки с середины - не дыра в нумерации"
    assert report.segments == 5 and report.duration == 60.0


def test_a_hole_in_the_numbering_is_a_gap() -> None:
    """Пропущенный номер в именах кусков и есть дыра, которую сверка ищет."""
    answers = _Answers(_manifest(["v0.ts", "v1.ts", "v3.ts"]))
    audit, report = _audit(answers)

    audit.run(URL, 0.0, lambda: AHEAD, threading.Event())

    assert report.gaps == 1 and report.segments == 3


def test_a_reply_without_cors_is_counted_against_the_run() -> None:
    """Приёмник на ответе без CORS молча молчит, поэтому такие ответы считаются."""
    answers = _Answers(_manifest(["v0.ts", "v1.ts"]), cors=False)
    audit, report = _audit(answers)

    audit.run(URL, 0.0, lambda: AHEAD, threading.Event())

    assert report.no_cors == 2 and not report.ok


def test_the_peak_is_taken_from_the_heaviest_piece() -> None:
    """Пик считается по весу куска и его длительности - это и есть скорость на ТВ."""
    answers = _Answers(_manifest(["v0.ts"], span=10.0), size=20 << 20)
    audit, report = _audit(answers)

    audit.run(URL, 0.0, lambda: AHEAD, threading.Event())

    assert report.peak_mbit == 20 * 1024 * 1024 * 8 / 10 / 1e6


def test_a_segment_the_source_refuses_is_a_gap() -> None:
    """Сегмент из манифеста обязан отдаваться: не отдался - это разрыв, а не мелочь."""

    class _Refusing(_Answers):
        def head(self, url: str, timeout: float = 0.0) -> _Served:
            raise requests.ConnectionError("нет куска")

    answers = _Refusing(_manifest(["v0.ts", "v1.ts"]))
    audit, report = _audit(answers)

    audit.run(URL, 0.0, lambda: AHEAD, threading.Event())

    assert report.gaps == 2


def test_a_manifest_that_never_came_closes_the_run() -> None:
    """Без манифеста показа нет вовсе: сверка не падает, а закрывает заход."""

    class _Silent(_Answers):
        def get(self, url: str, timeout: float = 0.0) -> _Served:
            raise requests.ConnectionError("раздача молчит")

    answers = _Silent("")
    audit, report = _audit(answers)
    done = threading.Event()

    audit.run(URL, 0.0, lambda: AHEAD, done)

    assert done.is_set() and report.segments == 0


def test_the_audit_holds_behind_the_decoder_and_stops_with_it() -> None:
    """Сверка спрашивает только то, до чего дошёл декодер, - и умолкает, когда показ снят."""
    answers = _Answers(_manifest([f"v{slot}.ts" for slot in range(6)]))
    audit, report = _audit(answers)
    done = threading.Event()
    done.set()  # показ снят раньше, чем сверка дошла до первого куска

    audit.run(URL, 0.0, lambda: 0.0, done)

    assert _heads(answers) == [], "снятый показ сегментов больше не спрашивает"
    assert report.duration == 60.0, "манифест сверка успела прочитать"
