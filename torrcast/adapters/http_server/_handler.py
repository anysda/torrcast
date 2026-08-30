"""Отвечает приёмнику на запрос манифеста и сегмента; поднимает его :class:`HlsServer`."""

from __future__ import annotations

import http.server
import os
import re
import time
from pathlib import Path
from typing import Any, ClassVar, Final

from torrcast.adapters.http_server._feed import _Feed
from torrcast.adapters.http_server.log_segment import log_segment
from torrcast.adapters.stream_probe.segment_slot import segment_slot
from torrcast.domain.catalogs.phrase import phrase
from torrcast.domain.debug_handles import TRACE_ENV
from torrcast.domain.trace_sources import PACKED, WARMED_COPY, WARMED_RECODE

#: Отдаём ровно манифест и сегменты сетки, и ничего больше: каталог наружу не открыт.
_ASSET_RE: Final = re.compile(r"^(?:v\d+\.(?:ts|m4s)|init\.mp4|(?:index|stream)\.m3u8)$")
_TYPES: Final = {
    ".m3u8": "application/vnd.apple.mpegurl",
    ".ts": "video/mp2t",
    ".m4s": "video/mp4",
    ".mp4": "video/mp4",
}
_RANGE_RE: Final = re.compile(r"bytes=(\d*)-(\d*)")


def _tracing() -> bool:
    """Просит ли человек след раздачи прямо сейчас (``TORRCAST_TRACE=1``).

    Спрашивается в момент показа, а не в момент импорта: ручку ставят юниту показа
    (:data:`~torrcast.domain.unit_naming._PASS_ENV`), и прочитанная на импорте она
    навсегда осталась бы такой, какой была у первого, кто затащил модуль в процесс.
    """
    return bool(os.environ.get(TRACE_ENV))


class _Handler(http.server.BaseHTTPRequestHandler):
    """Манифест и сегменты: CORS на всех ответах, Range на сегментах, ноль лишних путей.

    Range обязателен: ресивер Q70D переспрашивает куски диапазонами (известная
    особенность приёмника), а без ``Access-Control-Allow-Origin: *`` Chromecast молча
    не играет.

    Манифест берётся не с диска, а у :class:`Feed`: он описывает весь фильм, а не то,
    что успело упаковаться. Запрос сегмента тоже уходит в ``Feed`` —
    именно там запрос неупакованного места превращается в перемотку.
    """

    protocol_version = "HTTP/1.1"
    server_version = "torrcast"
    root: Path = Path()
    feed: ClassVar[_Feed | None] = None
    #: Снимок меток точечного перекода, пополняемый прогревом без дискового чтения.
    warm_recodes: ClassVar[set[int]] = set()
    #: Откуда взят кусок, который сейчас отдаём
    #: (:data:`torrcast.domain.trace_sources.PACKED` и два вида прогретого). Ставит
    #: :meth:`_read`, читает
    #: :func:`log_segment`.
    _src: str = "pack"

    def do_GET(self) -> None:
        self._serve(body=True)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def do_OPTIONS(self) -> None:
        self._head(204, 0, "text/plain")

    def _serve(self, body: bool) -> None:
        began = time.monotonic()
        name = self.path.split("?")[0].lstrip("/")
        if not _ASSET_RE.fullmatch(name):
            self._head(404, 0, "text/plain")
            return
        data = self._read(name)
        if data is None:
            self._head(404, 0, "text/plain")
            self._trace(name, began, "404")
            return
        self._trace(
            name, began, phrase("http_server.trace_megabytes", size=f"{len(data) / 1e6:.1f}")
        )
        suffix = Path(name).suffix
        ctype, total = _TYPES[suffix], len(data)
        span = self._range(total)
        if span is None:
            self._head(200, total, ctype)
        elif not span:
            self._head(416, 0, ctype, (("Content-Range", f"bytes */{total}"),))
            return
        else:
            first, last = span
            data = data[first : last + 1]
            self._head(206, len(data), ctype, (("Content-Range", f"bytes {first}-{last}/{total}"),))
        if body:
            sent = time.monotonic()
            self.wfile.write(data)
            took = time.monotonic() - sent
            self._sent(name, len(data), took)
            log_segment(name, began, len(data), took, self._src)

    def _read(self, name: str) -> bytes | None:
        """Тело ответа: манифест на весь фильм или сегмент, дождавшись упаковки.

        Заодно запоминает, ОТКУДА взят кусок (:attr:`_src`): решает это
        :meth:`Feed.segment`, а в след пишет :func:`log_segment`, и передать источник
        между ними больше нечем - наружу уходят одни байты.
        """
        if name.endswith(".m3u8"):
            return self.feed.manifest(name) if self.feed is not None else None
        if name == "init.mp4":
            path = self.feed.init() if self.feed is not None else self.root / name
            if path is None:
                return None
            try:
                return path.read_bytes()
            except OSError:
                return None
        path = self.root / name
        if self.feed is not None:
            found = self.feed.segment(segment_slot(name))
            if found is None:
                return None
            path = found
            self._src = (
                PACKED
                if found.parent == self.feed.out
                else WARMED_RECODE
                if segment_slot(name) in self.warm_recodes
                else WARMED_COPY
            )
        try:
            return path.read_bytes()
        except OSError:  # вычистило окном ровно между проверкой и чтением
            return None

    def _range(self, size: int) -> tuple[int, int] | tuple[()] | None:
        found = _RANGE_RE.fullmatch(self.headers.get("Range", "").strip())
        if not found:
            return None
        head, tail = found.group(1), found.group(2)
        if not head:
            first, last = max(0, size - int(tail or 0)), size - 1
        else:
            first, last = int(head), min(int(tail) if tail else size - 1, size - 1)
        return (first, last) if first <= last < size else ()

    def _head(self, code: int, length: int, ctype: str, extra: tuple[Any, ...] = ()) -> None:
        self.send_response(code)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(length))
        # Кэшировать нельзя ничего: манифест дописывается на ходу, а после перепаковки
        # (перемотка назад глубже окна) под теми же именами сегментов лежит
        # уже другое место фильма - кэш приёмника показал бы старое.
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()

    def _trace(self, name: str, began: float, got: str) -> None:
        """Что попросил приёмник, сколько ждал ответа и что получил (``TORRCAST_TRACE=1``).

        Без этого подвис не измерить: снаружи он выглядит одинаково и
        когда он ждёт нас, и когда он перестал спрашивать вовсе, — а лечится это по-разному.
        """
        if not _tracing():
            return
        span = self.headers.get("Range", "")
        waited = f"{time.monotonic() - began:.1f}"
        span_text = f" {span}" if span else ""
        line = phrase(
            "http_server.trace_request", name=name, span=span_text, waited=waited, got=got
        )
        print(line, flush=True)

    def _sent(self, name: str, size: int, seconds: float) -> None:
        """Сколько времени кусок **уезжал в телевизор** (``TORRCAST_TRACE=1``).

        Не то же самое, что :meth:`_trace`: тот меряет, сколько мы искали кусок, а этот —
        сколько заняла отдача по сети. Без этого числа не отличить «показ споткнулся о
        нарезку» от «канал до ТВ не тянет этот кусок»: с диска всё отдаётся мгновенно, а
        уезжает ровно столько, сколько позволяет линк.
        """
        if not _tracing() or seconds <= 0:
            return
        size_mb, rate = f"{size / 1e6:.1f}", f"{size * 8 / seconds / 1e6:.1f}"
        line = phrase(
            "http_server.trace_sent", name=name, size=size_mb, seconds=f"{seconds:.1f}", rate=rate
        )
        print(line, flush=True)

    def log_message(self, fmt: str, *args: Any) -> None:
        pass
