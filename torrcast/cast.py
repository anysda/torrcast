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
import time
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
    "trust_anchor",
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

    #: Пока показ ни разу не начался, ``IDLE`` — это «ещё грузится», а не отказ: ресивер
    #: сначала тянет манифест и первый сегмент, и до этого статус остаётся IDLE. Замерено
    #: на живом Q70D 05-08-2026: ``play_media`` возвращается через 0.03 с, а PLAYING
    #: приходит через 0.7–1.5 с — то есть «сразу после LOAD» приёмник всегда не играет.
    START_TIMEOUT = 90.0
    #: LOAD ERROR лечится повтором LOAD (рецепт kinocast на этом же ТВ: ровно 2 попытки).
    LOAD_RETRIES = 2
    #: app_id Default Media Receiver: чужой app = каст сняли пультом, показ окончен.
    MEDIA_APP = "CC1AD845"

    def __init__(self, address: str) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv <ip>")
        self.address = address
        self._cast: Any = None
        self._url = ""
        self._title = ""

    def play(self, url: str, title: str = "") -> None:
        """Начать показ и **дождаться картинки**, а не просто отправить LOAD.

        Без ожидания показ гаснет через секунду после команды: сторож снимает позицию
        сразу после ``play_media``, видит закономерный IDLE и считает, что играть нечего.
        """
        self._url, self._title = url, title or "torrcast"
        self._load()
        if self._settle():
            return
        raise InfraError(f"ТВ {self.address} не начал показ: {self._why()}")

    def stop(self) -> None:
        if self._cast is not None:
            with contextlib.suppress(Exception):
                self._cast.media_controller.stop()

    def position(self) -> Position:
        st = self._status()
        return Position(st.current_time or 0.0, st.duration or 0.0, st.player_is_playing)

    def _load(self) -> None:
        controller = self._device().media_controller
        # BUFFERED, а не LIVE: манифест типа EVENT только дописывается, и ресивер
        # показывает шкалу — перемотка пультом остаётся рабочей (§2.5).
        controller.play_media(
            self._url, HLS_TYPE, title=self._title, stream_type="BUFFERED", media_info=HLS_HINTS
        )
        controller.block_until_active(timeout=30)

    def _settle(self) -> bool:
        """Дождаться, пока приёмник действительно заиграет; LOAD ERROR — повторить LOAD."""
        deadline = time.monotonic() + self.START_TIMEOUT
        retries = 0
        while time.monotonic() < deadline:
            time.sleep(1.0)
            status = self._status()
            if status.player_state in ("PLAYING", "BUFFERING"):
                return True
            if status.idle_reason == "ERROR":
                if retries >= self.LOAD_RETRIES:
                    return False
                retries += 1
                self._load()
        return False

    def _status(self) -> Any:
        """Свежий статус приёмника. ``update_status`` обязателен: без него pychromecast
        отдаёт последний присланный статус, и позиция замирает навсегда — сторож считает,
        что показ стоит, окно сегментов не чистится и tmpfs растёт до конца фильма.
        """
        controller = self._device().media_controller
        # ⚠️ На закрытом ресивере update_status ПЕРЕЗАПУСКАЕТ пустой Default Media
        # Receiver — «вышел в Home, а каст открылся снова» (грабли kinocast). Поэтому
        # чужой app_id проверяем раньше и статус не трогаем.
        if getattr(self._cast.status, "app_id", None) != self.MEDIA_APP:
            return controller.status
        with contextlib.suppress(Exception):
            controller.update_status()
        return controller.status

    def _why(self) -> str:
        status = self._status()
        state = status.player_state or "нет статуса"
        return f"{state}/{status.idle_reason}" if status.idle_reason else str(state)

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

    TLS проверяется по-настоящему, а не ``verify=False``: чему доверять, решает
    :func:`trust_anchor` — системному хранилищу для настоящего LE-серта (ровно как ТВ)
    или самому файлу для self-signed. Пустой ``ca`` = системное хранилище (§9).
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


def trust_anchor(cert: str) -> str:
    """Чему приёмник должен доверять, проверяя нашу раздачу.

    Серт выпущен настоящим CA (LE на стенде) — доверяем **системному хранилищу**: ровно
    так его проверит ТВ, и только такая проверка закрывает риск §9 «Chromecast требует
    доверенный HTTPS». Серт self-signed (дефолт `install.sh` до доставки LE) — доверяем
    ему самому: иначе проверять нечем.

    Различаем по файлу: OpenSSL берёт в доверенные только CA-сертификаты, поэтому у
    self-signed остаётся он сам (subject == issuer), а у цепочки LE — промежуточный
    (subject != issuer), листа в списке нет вовсе.
    """
    import ssl

    try:
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.load_verify_locations(cafile=cert)
        anchors = context.get_ca_certs()
    except (OSError, ssl.SSLError):
        return cert  # нечитаемый серт — пусть падает там, где это видно
    if len(anchors) == 1 and anchors[0].get("subject") == anchors[0].get("issuer"):
        return cert
    return ""


def make_receiver(kind: ReceiverKind, address: str = "", ca: str = "") -> Receiver:
    if kind == "mock":
        return MockReceiver(trust_anchor(ca) if ca else "")
    return ChromecastReceiver(address)
