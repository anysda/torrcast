"""Приёмники: реальный Chromecast и mock — интерфейс с двумя реализациями (§3 ТЗ).

``mock`` не заглушка «для галочки»: headless-клиент тянет манифест и сегменты по https
ровно как ТВ, проверяет CORS и непрерывность нумерации, декодирует ffmpeg'ом и отдаёт
позицию — на нём проходит вся автономная приёмка (§7, реестр ТВ-рисков §9).
Samsung-специфики здесь нет и быть не должно (§1): ни PowerState, ни nudge-сторожей.
"""

from __future__ import annotations

import contextlib
import re
import subprocess
import tempfile
import threading
from dataclasses import dataclass
from typing import IO, Any, Literal, Protocol, runtime_checkable

from torrcast import InfraError, why
from torrcast.stream import parse_manifest

__all__ = [
    "HLS_HINTS",
    "HLS_TYPE",
    "ChromecastReceiver",
    "MockReceiver",
    "Position",
    "Receiver",
    "Report",
    "make_receiver",
]

ReceiverKind = Literal["chromecast", "mock"]

#: Тип манифеста и подсказки формата сегментов: без них Default Media Receiver
#: отвечает LOAD ERROR на муксованный TS (грабли kinocast на этом же Q70D).
HLS_TYPE = "application/vnd.apple.mpegurl"
HLS_HINTS = {"hlsVideoSegmentFormat": "mpeg2_ts", "hlsSegmentFormat": "ts"}

#: Номер сегмента в имени ``index<N>.ts`` — по нему ловятся дыры в нумерации.
_NUM_RE = re.compile(r"(\d+)\.ts$")
#: Строки ffmpeg, означающие, что кусок не доехал: для приёмки это разрыв.
_LOST_RE = re.compile(r"Failed to open segment|Error opening|Cannot reload|skipping", re.I)
_CORS_HEADER = "Access-Control-Allow-Origin"


@dataclass(frozen=True, slots=True)
class Position:
    pos: float
    dur: float
    playing: bool = False

    @property
    def ratio(self) -> float:
        return self.pos / self.dur if self.dur > 0 else 0.0


@runtime_checkable
class Receiver(Protocol):
    """Что нам нужно от приёмника — и ничего сверх того."""

    def play(self, url: str, title: str = "") -> None:
        """Начать воспроизведение HLS-манифеста."""

    def stop(self) -> None:
        """Снять каст."""

    def position(self) -> Position:
        """Текущая позиция и длительность."""


@dataclass(slots=True)
class Report:
    """Что mock увидел как приёмник — цифры приёмки §7.2."""

    segments: int = 0
    duration: float = 0.0
    decoded: float = 0.0
    gaps: int = 0
    peak_mbit: float = 0.0
    #: Ответы без ``Access-Control-Allow-Origin``: Chromecast на таких молча молчит (§9).
    no_cors: int = 0

    @property
    def ok(self) -> bool:
        """Приёмка §7.2: дыр нет, CORS везде, декодировано до конца (хвост в один сегмент)."""
        return (
            self.segments > 0
            and self.gaps == 0
            and self.no_cors == 0
            and self.decoded >= self.duration - 8.0
        )

    def line(self) -> str:
        return (
            f"сегментов {self.segments} · манифест {self.duration:.0f} с · "
            f"декодировано {self.decoded:.0f} с · разрывов {self.gaps} · "
            f"без CORS {self.no_cors} · пик {self.peak_mbit:.1f} Мбит/с"
        )


class ChromecastReceiver:
    """Реальный приёмник: pychromecast по адресу из конфига.

    Почему не catt: его ``cast <url>`` гонит любой URL через yt-dlp и не умеет передать
    подсказки формата HLS (:data:`HLS_HINTS`), без которых ресивер отвечает LOAD ERROR.
    ⚠️ Порт 8009 открыт даже в standby, любой коннект будит ТВ (§8) — поэтому соединение
    поднимается лениво, только когда кастить действительно собираются, а до этапа 6
    адрес ТВ в конфиге отсутствует физически.
    """

    def __init__(self, address: str) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv <ip>")
        self.address = address
        self._cast: Any = None

    def play(self, url: str, title: str = "") -> None:
        controller = self._device().media_controller
        # BUFFERED, а не LIVE: манифест типа EVENT только дописывается, и ресивер
        # показывает шкалу — перемотка пультом остаётся рабочей (§2.5).
        controller.play_media(
            url, HLS_TYPE, title=title or "torrcast", stream_type="BUFFERED", media_info=HLS_HINTS
        )
        controller.block_until_active(timeout=30)

    def stop(self) -> None:
        if self._cast is not None:
            with contextlib.suppress(Exception):
                self._cast.media_controller.stop()

    def position(self) -> Position:
        st = self._device().media_controller.status
        return Position(st.current_time or 0.0, st.duration or 0.0, st.player_is_playing)

    def _device(self) -> Any:
        if self._cast is None:
            import uuid

            import pychromecast

            try:
                device = pychromecast.get_chromecast_from_host(
                    (self.address, 8009, uuid.UUID(int=0), None, None), timeout=10
                )
                device.wait(timeout=20)
            except Exception as exc:
                raise InfraError(f"ТВ {self.address} не принял каст: {why(exc)}") from exc
            self._cast = device
        return self._cast


class MockReceiver:
    """Headless-приёмник: тянет HLS по https как ТВ и декодирует ffmpeg'ом в ``/dev/null``.

    TLS проверяется по-настоящему: тот же файл серта отдаётся ffmpeg'у как ``-ca_file``
    и requests как CA-bundle, так что self-signed на стенде и LE в проде проходят одну
    и ту же проверку — меняется только путь в конфиге (§9: доверенный HTTPS).
    """

    def __init__(self, ca: str = "") -> None:
        self.ca = ca
        self.report = Report()
        self._proc: subprocess.Popen[str] | None = None
        self._err: IO[bytes] | None = None
        self._pos = Position(0.0, 0.0, False)
        self._done = threading.Event()
        self._seen: set[str] = set()
        self._last = -1

    def play(self, url: str, title: str = "") -> None:
        self._probe(url)  # первый ответ проверяем сами: TLS, доступность, CORS
        self._err = tempfile.TemporaryFile()  # noqa: SIM115 — живёт всё воспроизведение
        ca = ["-ca_file", self.ca] if self.ca else []
        command = [
            "ffmpeg", "-hide_banner", "-nostats", "-loglevel", "warning",
            "-tls_verify", "1", *ca, "-i", url, "-progress", "pipe:1", "-f", "null", "-",
        ]  # fmt: skip
        try:
            self._proc = subprocess.Popen(
                command, stdout=subprocess.PIPE, stderr=self._err, text=True
            )
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        self._pos = Position(0.0, 0.0, True)
        for target in (self._follow, self._audit):
            threading.Thread(target=target, args=(url,), daemon=True).start()

    def stop(self) -> None:
        self._done.set()
        if self._proc is not None and self._proc.poll() is None:
            self._proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self._proc.wait(timeout=5)
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def position(self) -> Position:
        # dur — то, что уже упаковано и лежит в манифесте: по разнице с позицией
        # показ придерживает упаковку, чтобы окно сегментов не убежало вперёд.
        return Position(self._pos.pos, self.report.duration, self._pos.playing)

    def _session(self) -> Any:
        import requests

        session = requests.Session()
        session.verify = self.ca or True
        return session

    def _probe(self, url: str) -> None:
        import requests

        try:
            response = self._session().get(url, timeout=30)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise InfraError(f"приёмник не забрал манифест: {why(exc)}") from exc
        if response.headers.get(_CORS_HEADER) != "*":
            raise InfraError(f"в ответе нет {_CORS_HEADER}: * — Chromecast такое молча не играет")

    def _follow(self, url: str) -> None:
        """Позиция из ``-progress`` декодера: ровно то, что ТВ отдал бы сторожу (§2.5)."""
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            if line.startswith("out_time_us="):
                with contextlib.suppress(ValueError):
                    self._pos = Position(int(line[12:]) / 1e6, self._pos.dur, True)
        proc.wait()
        self._done.set()
        self.report.decoded = self._pos.pos
        if self._err is not None:
            self._err.seek(0)
            text = self._err.read().decode("utf-8", "replace")
            self.report.gaps += len(_LOST_RE.findall(text))
        self._pos = Position(self._pos.pos, self._pos.dur, False)

    def _audit(self, url: str) -> None:
        """Сегменты забираются по сети, как ТВ: HEAD на каждый новый — CORS, размер, нумерация."""
        session, base = self._session(), url.rsplit("/", 1)[0]
        while True:
            # Последний проход делаем уже после конца показа: хвост манифеста тоже наш.
            finished = self._done.wait(2.0)
            try:
                body = session.get(url, timeout=30)
                self._check(body)
                segments, _ = parse_manifest(body.text)
            except Exception:  # пока идёт показ, манифест обязан отдаваться
                segments = []
                self.report.gaps += 0 if finished else 1
            self.report.duration = max(self.report.duration, sum(s for _, s in segments))
            for name, seconds in segments:
                if name in self._seen:
                    continue
                self._seen.add(name)
                self.report.segments += 1
                number = _NUM_RE.search(name)
                if number and self._last >= 0 and int(number.group(1)) != self._last + 1:
                    self.report.gaps += 1
                self._last = int(number.group(1)) if number else self._last
                self._measure(session, f"{base}/{name}", seconds)
            if finished:
                return

    def _measure(self, session: Any, url: str, seconds: float) -> None:
        try:
            head = session.head(url, timeout=30)
            self._check(head)
            size = int(head.headers.get("Content-Length") or 0)
        except Exception:  # сегмент из манифеста обязан отдаваться — иначе это дыра
            self.report.gaps += 1
            return
        if seconds > 0:
            self.report.peak_mbit = max(self.report.peak_mbit, size * 8 / seconds / 1e6)

    def _check(self, response: Any) -> None:
        response.raise_for_status()
        if response.headers.get(_CORS_HEADER) != "*":
            self.report.no_cors += 1


def make_receiver(kind: ReceiverKind, address: str = "", ca: str = "") -> Receiver:
    return MockReceiver(ca) if kind == "mock" else ChromecastReceiver(address)
