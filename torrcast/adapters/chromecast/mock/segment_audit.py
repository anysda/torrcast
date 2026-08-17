"""Сверка сегментов: приёмник забирает куски по сети и считает цифры приёмки."""

from __future__ import annotations

import re
import threading
from collections.abc import Callable
from typing import Any, Final

from torrcast.adapters.chromecast.mock.hls_fetch import CORS_HEADER, HTTP_TIMEOUT, HlsFetch
from torrcast.adapters.stream_pack import parse_manifest
from torrcast.domain.reception_report import ReceptionReport
from torrcast.domain.trimmed_playlist import GRID_SLACK

#: Номер сегмента в имени ``index<N>.ts`` - по нему ловятся дыры в нумерации.
_NUM_RE: Final = re.compile(r"(\d+)\.ts$")
#: На сколько секунд вперёд декодера разрешено спрашивать сегменты.
AHEAD_SECONDS: Final = 8.0


class SegmentAudit:
    """Сегменты забираются по сети, как ТВ: HEAD на каждый - CORS, размер, нумерация.

    ⚠️ Идти по манифесту подряд и сразу нельзя: он описывает **весь фильм**, а файлы
    появляются там, где показ идёт прямо сейчас. Спросить всё разом значит потребовать
    упаковать фильм целиком, чего tmpfs и не выдержит. Поэтому сверка, как и живой
    приёмник, спрашивает только то, до чего дошёл декодер.
    """

    def __init__(self, report: ReceptionReport, fetch: HlsFetch) -> None:
        self.report = report
        self.fetch = fetch

    def run(
        self, url: str, start: float, position: Callable[[], float], done: threading.Event
    ) -> None:
        """Пройти манифест до конца показа, держась за декодером.

        🔴 Кусок, который КОНЧАЕТСЯ на месте захода, приёмнику не нужен: он весь позади.
        Строгое «кончился раньше» оставляло его в списке (на сетке по 10 с заход на 10.0 с
        честно спрашивал нулевой кусок), и раздача уходила паковать с нуля - тот самый
        лишний заход упаковки, ради которого декодеру и срезают голову плейлиста. Допуск
        тут тот же: границы сетки складываются из округлённых ``EXTINF`` и на секунду
        захода бит в бит не ложатся.
        """
        session, base = self.fetch.open(), url.rsplit("/", 1)[0]
        try:
            body = session.get(url, timeout=HTTP_TIMEOUT)
            self.seen(body)
            segments, _ = parse_manifest(body.text)
        except Exception:  # без манифеста показа нет вовсе - это уже поймал HlsFetch
            done.set()
            return
        self.report.duration = sum(seconds for _, seconds in segments)
        at, last = 0.0, -1
        for name, seconds in segments:
            end = at + seconds
            at = end
            if end <= start + GRID_SLACK:  # кусок весь позади захода - он не нужен
                continue
            while not done.is_set() and position() + AHEAD_SECONDS < end:
                done.wait(0.5)
            if done.is_set():
                return
            self.report.segments += 1
            number = _NUM_RE.search(name)
            if number and last >= 0 and int(number.group(1)) != last + 1:
                self.report.gaps += 1
            last = int(number.group(1)) if number else last
            self.measure(session, f"{base}/{name}", seconds)

    def measure(self, session: Any, url: str, seconds: float) -> None:
        """Вес куска в пике: сегмент из манифеста обязан отдаваться, иначе это дыра."""
        try:
            head = session.head(url, timeout=HTTP_TIMEOUT)
            self.seen(head)
            size = int(head.headers.get("Content-Length") or 0)
        except Exception:
            self.report.gaps += 1
            return
        if seconds > 0:
            self.report.peak_mbit = max(self.report.peak_mbit, size * 8 / seconds / 1e6)

    def seen(self, response: Any) -> None:
        """Что ответ рассказал приёмнику: код, память о 404 и CORS."""
        self.fetch.caught(response)
        response.raise_for_status()
        if response.headers.get(CORS_HEADER) != "*":
            self.report.no_cors += 1
