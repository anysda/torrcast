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
    #: Состояние приёмника как есть (``PLAYING``/``BUFFERING``/``PAUSED``/``IDLE``).
    #: Показу нужно отличать паузу на пульте от конца фильма: на паузе упаковка гасится,
    #: но показ жив и продолжится с того же места (§6 SPEC-v2).
    state: str = ""

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
    #: Пауза между повторами LOAD: ресиверу нужно время закрыть прошлую сессию.
    LOAD_PAUSE = 3.0
    #: Столько терпим молчаливый IDLE после LOAD, прежде чем считать, что его не взяли.
    #: ⚠️ Это не противоречит «IDLE до первого показа — это загрузка»: живой Q70D отвечает
    #: PLAYING за 0.7–1.5 с, а 30 с молчания означают, что грузить он не начинал.
    STUCK_SECONDS = 30.0
    #: app_id Default Media Receiver: чужой app = каст сняли пультом, показ окончен.
    MEDIA_APP = "CC1AD845"
    #: Неподвижный BUFFERING дольше этого — приёмник завис (см. :meth:`_nudge`).
    #: ⚠️ Порог намеренно велик: штатный ребуфер на живом Q70D укладывается в 1–3 с, а
    #: настоящее зависание длится бесконечно (замерено: 60+ с без единого запроса).
    #: Мелкий порог превращает обычный ребуфер в нудж, а каждый нудж стоит перемотки.
    STALL_SECONDS = 20.0
    #: Шаг прыжка вперёд на каждом нудже: мимо куска, на котором приёмник споткнулся.
    STALL_SKIP = 8.0

    def __init__(self, address: str) -> None:
        if not address:
            raise InfraError("адрес ТВ не задан: cast --tv <ip>")
        self.address = address
        self._cast: Any = None
        self._url = ""
        self._title = ""
        self._peak = 0.0
        self._stall_at = -1.0
        self._stall_since = 0.0
        self._stall_hits = 0
        self._reloads = 0
        self._started = False

    def play(self, url: str, title: str = "") -> None:
        """Начать показ и **дождаться картинки**, а не просто отправить LOAD.

        Без ожидания показ гаснет через секунду после команды: сторож снимает позицию
        сразу после ``play_media``, видит закономерный IDLE и считает, что играть нечего.

        Зовётся не только в начале: после перепаковки потока (перемотка назад глубже окна,
        возврат с паузы) поток начинается заново — и счётчики сторожа тоже.

        ⚠️ Второй и следующий LOAD за показ идут только в **свежее приложение** приёмника.
        Замерено 05-08-2026 дважды: приёмник, поймавший 404 на перемотке назад, встаёт в
        IDLE и на любой следующий LOAD в то же приложение отвечает молчанием (90 с и смерть
        показа), а `quit_app` + LOAD поднимает картинку за те же 6 с, что и холодный старт.
        """
        self._url, self._title = url, title or "torrcast"
        self._peak, self._reloads, self._stall_hits = 0.0, 0, 0
        self._stall_at, self._stall_since = -1.0, 0.0
        if self._started:
            self._restart_app()
        self._started = True
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
        state = str(st.player_state or "")
        pos = st.current_time or 0.0
        if pos > self._peak:  # реальный прогресс — прошлые нуджи больше не в счёт
            self._peak, self._stall_hits = pos, 0
        if state == "BUFFERING":
            self._nudge(pos)
        else:
            self._stall_at, self._stall_since = -1.0, 0.0
        if state == "IDLE" and st.idle_reason == "ERROR" and self._reload():
            return Position(self._peak, st.duration or 0.0, True, "BUFFERING")
        return Position(pos, st.duration or 0.0, st.player_is_playing, state)

    def _reload(self) -> bool:
        """Повтор LOAD посреди показа: приёмник отвалился с ``IDLE/ERROR``.

        Рецептура kinocast на этом же ТВ: ровно две попытки, дальше это не наша авария.
        Грузим с ``current_time``, иначе LOAD на EVENT-манифесте начал бы показ сначала —
        а мы всего лишь поднимаем приёмник на том месте, где он споткнулся.
        """
        if self._reloads >= self.LOAD_RETRIES:
            return False
        self._reloads += 1
        print(f"приёмник отвалился на {self._peak:.0f} с — повтор LOAD", flush=True)
        try:
            self._restart_app()  # чистое приложение: залипший молчит на любой LOAD
            self._load(self._peak)
        except Exception:  # приёмник мог просто уйти — решает следующий тик
            return False
        return True

    def _nudge(self, pos: float) -> None:
        """Расшевелить приёмник, зависший в BUFFERING на одной и той же секунде.

        Замерено на живом Q70D 05-08-2026: на 273-й секунде показа ресивер перестал
        запрашивать сегменты и встал в BUFFERING **навсегда** — при том что следующий
        кусок лежал в tmpfs и отдавался curl'ом за миллисекунды, а живого соединения от ТВ
        в conntrack не было вовсе. То есть подвисает сам приёмник, и лечится это ``seek``:
        показ возобновляется немедленно. Тот же сторож годами держит kinocast на этом ТВ.

        ⚠️ Прыгать можно **только вперёд**. На растущем манифесте ресивер отрабатывает
        ``seek`` не точно, а с начала подходящего сегмента, и «нудж на месте» откатывал
        показ на ~35 с назад. Позиция после отката меньше пройденного максимума, счётчик
        не сбрасывался бы — и получалась бесконечная лесенка назад (наблюдалась живьём:
        2:12 → 1:58 → 1:44). Поэтому целимся от максимума и всегда с шагом вперёд.
        """
        now = time.monotonic()
        if pos != self._stall_at:
            self._stall_at, self._stall_since = pos, now
            return
        if now - self._stall_since < self.STALL_SECONDS:
            return
        self._stall_hits += 1
        self._stall_since = now
        with contextlib.suppress(Exception):
            self._device().media_controller.seek(self._peak + self.STALL_SKIP * self._stall_hits)

    def _load(self, at: float = 0.0) -> None:
        controller = self._device().media_controller
        # BUFFERED, а не LIVE: манифест типа EVENT только дописывается, и ресивер
        # показывает шкалу — перемотка пультом остаётся рабочей (§2.5).
        controller.play_media(
            self._url,
            HLS_TYPE,
            title=self._title,
            stream_type="BUFFERED",
            media_info=HLS_HINTS,
            current_time=at,
        )
        controller.block_until_active(timeout=30)

    def _settle(self) -> bool:
        """Дождаться, пока приёмник действительно заиграет; отказ LOAD — повторить LOAD.

        ``IDLE`` без причины — это «ещё грузится», его терпим до :data:`START_TIMEOUT`.
        А вот причина говорит, что LOAD не взяли, и ждать бессмысленно:

        * ``ERROR`` — ресивер не смог начать (рецепт kinocast: ровно 2 попытки);
        * ``IDLE`` дольше :data:`STUCK_SECONDS` — LOAD не взяли молча. Такое поймано
          05-08-2026 после перепаковки: приёмник стоял в IDLE все 90 с при живых сегментах.

        ⚠️ ``INTERRUPTED`` поводом для повтора НЕ является: так ресивер отчитывается о
        КОНЦЕ ПРЕЖНЕЙ сессии, которую оборвал наш же новый LOAD. Повтор на него сбивает
        только что принятый LOAD — проверено живьём, показ на этом и умер.

        Любая повторная попытка идёт в чистое приложение: залипший Default Media Receiver
        молчит на все LOAD подряд, а `quit_app` лечит сразу.
        """
        deadline = time.monotonic() + self.START_TIMEOUT
        tried = time.monotonic()
        while time.monotonic() < deadline:
            time.sleep(1.0)
            status = self._status()
            if status.player_state in ("PLAYING", "BUFFERING"):
                return True
            waited = time.monotonic() - tried
            refused = status.idle_reason == "ERROR" and waited >= self.LOAD_PAUSE
            if refused or waited >= self.STUCK_SECONDS:
                if self._reloads >= self.LOAD_RETRIES:
                    return False
                self._reloads += 1
                tried = time.monotonic()
                print(f"LOAD не взяли ({self._why()}) — гружу заново", flush=True)
                self._restart_app()
                self._load()
        return False

    def _restart_app(self) -> None:
        """Закрыть приложение приёмника, чтобы следующий LOAD пришёл в чистое."""
        print("приёмник залип — закрываю приложение и гружу заново", flush=True)
        with contextlib.suppress(Exception):
            self._device().quit_app()
        time.sleep(self.LOAD_PAUSE)

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
        # dur — то, что уже упаковано и лежит в манифесте: показ по нему видит, насколько
        # упаковка ушла вперёд от приёмника.
        playing = self._pos.playing
        return Position(self._pos.pos, self.report.duration, playing, "PLAYING" if playing else "")

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
