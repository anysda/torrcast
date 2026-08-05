"""TorrServer, ffprobe и упаковка потока в HLS. Своего CDN-кода нет: раздачу отдаёт
TorrServer (кэш в RAM, на диск не пишем), пакует ffmpeg (§3 ТЗ). Формат для ТВ
зафиксирован: HLS, сегменты MPEG-TS ~4 с, один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import re
import signal
import ssl
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from torrcast import InfraError, why

if TYPE_CHECKING:
    import requests

__all__ = [
    "HLS_SEGMENT_SECONDS",
    "RUNTIME_GUESS",
    "AudioTrack",
    "HlsServer",
    "Media",
    "Packer",
    "TorrFile",
    "TorrServer",
    "Warmup",
    "bitrate_mbit",
    "ffmpeg_hls_command",
    "hls_dir",
    "parse_manifest",
    "pick_video_file",
    "probe",
]

#: Длительность сегмента HLS, секунды (§3 — зафиксировано, не настраивается).
HLS_SEGMENT_SECONDS: Final = 4
#: Аудио всегда перекодируется: passthrough AC3/DTS запрещён (§3).
AUDIO_CODEC: Final = "aac"
AUDIO_BITRATE: Final = "192k"
AUDIO_CHANNELS: Final = 2
#: Типовая длительность до ffprobe (фильм 2 ч, серия 45 мин): только для прикидки битрейта.
RUNTIME_GUESS: Final = {"movie": 7200.0, "tv": 2700.0, "other": 7200.0}

_TIMEOUT: Final = 30.0
_UNIT_NAME: Final = "torrcast-play"
_VIDEO_EXT: Final = (".mkv", ".mp4", ".avi", ".ts", ".m2ts", ".mov", ".webm")


def bitrate_mbit(size: int, duration: float) -> float:
    """Средний битрейт раздачи, Мбит/с — предел декодера Q70D ~20 (§3)."""
    return size * 8 / duration / 1e6 if size > 0 and duration > 0 else 0.0


@dataclass(frozen=True, slots=True)
class TorrFile:
    index: int
    name: str
    size: int = 0

    @property
    def season_episode(self) -> tuple[int, int] | None:
        """Сезон/серия из имени файла — список серий строится из раздачи (§2.4)."""
        from torrcast.parse import parse_episode

        found = parse_episode(self.name)
        return (found.season, found.episode) if found else None


@dataclass(frozen=True, slots=True)
class AudioTrack:
    index: int
    language: str | None = None
    title: str | None = None
    codec: str | None = None
    channels: int = 0

    @property
    def label(self) -> str:
        """Человеческая подпись для меню озвучек."""
        parts = [p for p in (self.language, self.title) if p]
        return " · ".join(parts) if parts else f"дорожка {self.index}"

    @property
    def is_russian(self) -> bool:
        """Русская дорожка — дефолт меню (§2.1)."""
        haystack = f"{self.language or ''} {self.title or ''}".casefold()
        return bool(re.search(r"\brus?\b|русск|дубляж", haystack))


@dataclass(slots=True)
class Warmup:
    """Фоновое добавление magnet в TorrServer под меню (§3.1)."""

    magnet: str
    torrent_hash: str = ""
    error: InfraError | None = None
    thread: threading.Thread | None = None

    def result(self, timeout: float = 30.0) -> str:
        """Дождаться hash прогретой раздачи."""
        if self.thread is not None:
            self.thread.join(timeout)
        if self.error is not None:
            raise self.error
        if not self.torrent_hash:
            raise InfraError("TorrServer не принял раздачу за отведённое время")
        return self.torrent_hash


@dataclass(frozen=True, slots=True)
class Media:
    """Что ffprobe вычитал из потока: длительность, звуковые дорожки и кодек видео."""

    duration: float = 0.0
    tracks: tuple[AudioTrack, ...] = ()
    #: Настоящий кодек видео. Имя раздачи врёт или молчит (у «Моаны 2» кодек назван
    #: в 2 именах из 8), а видео мы отдаём ``copy`` — значит ресивер получит ровно его.
    video: str | None = None

    @property
    def video_warning(self) -> str:
        """Пустая строка, если ресиверу это точно по зубам (§9: HEVC и экзотика)."""
        if self.video in (None, "h264"):
            return ""
        return f"⚠ видео {self.video}: ресивер может не взять — мы его не перекодируем"

    def default_track(self) -> int:
        """Дефолт меню озвучек — первая русская, иначе первая (§2.1)."""
        for track in self.tracks:
            if track.is_russian:
                return track.index
        return self.tracks[0].index if self.tracks else 0


class TorrServer:
    """Клиент TorrServer: добавить magnet, дождаться метаданных, отдать URL потока."""

    def __init__(self, base_url: str, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        """Добавить magnet и вернуть его hash. Метаданных на этот момент ещё нет."""
        payload = self._post("/torrents", {"action": "add", "link": magnet, "save_to_db": False})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на добавление")
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise InfraError("TorrServer не отдал hash раздачи")
        return torrent_hash

    def warm(self, magnet: str) -> Warmup:
        """Прогрев под меню (§3.1): magnet уходит фоном и набирает пиров, пока идут вопросы."""
        warmup = Warmup(magnet=magnet)
        thread = threading.Thread(target=self._warm, args=(warmup,), daemon=True)
        warmup.thread = thread
        thread.start()
        return warmup

    def _warm(self, warmup: Warmup) -> None:
        try:
            warmup.torrent_hash = self.add(warmup.magnet)
        except InfraError as exc:  # прогрев не обязан удаться — решает основной путь
            warmup.error = exc

    def files(self, torrent_hash: str) -> list[TorrFile]:
        """Список файлов раздачи; пуст, пока метаданные не приехали по DHT."""
        payload = self._post("/torrents", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на список файлов")
        raw = payload.get("file_stats")
        if not isinstance(raw, list):
            return []
        return [
            TorrFile(int(i.get("id") or 0), str(i.get("path", "")), int(i.get("length") or 0))
            for i in raw
            if isinstance(i, dict)
        ]

    def wait_files(self, torrent_hash: str, timeout: float = 60.0) -> list[TorrFile]:
        """Дождаться метаданных: пиры по DHT и ретрекерам (§3.1); нет за ``timeout`` — ошибка."""
        deadline = time.monotonic() + timeout
        while True:
            files = self.files(torrent_hash)
            if files:
                return files
            if time.monotonic() >= deadline:
                raise InfraError(f"раздача не отдала метаданные за {timeout:.0f} с — нет пиров")
            time.sleep(1.0)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        """HTTP-URL потока конкретного файла раздачи."""
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

    def drop(self, torrent_hash: str) -> None:
        """Убрать раздачу; отсутствие её ошибкой не считается."""
        with contextlib.suppress(InfraError):
            self._post("/torrents", {"action": "rem", "hash": torrent_hash})

    def _post(self, path: str, body: dict[str, Any]) -> Any:
        import requests

        if self._session is None:
            self._session = requests.Session()
        try:
            response = self._session.post(f"{self.base_url}{path}", json=body, timeout=self.timeout)
            response.raise_for_status()
            return response.json()
        except requests.RequestException as exc:
            raise InfraError(f"TorrServer не отвечает ({self.base_url}): {why(exc)}") from exc
        except ValueError as exc:
            raise InfraError("TorrServer вернул не JSON") from exc


def probe(url: str, timeout: float = 90.0) -> Media:
    """Дорожки и длительность из HTTP-потока, не качая файл: ffprobe берёт заголовок mkv
    запросами Range — это и есть цена меню озвучек (§3).
    """
    entries = (
        "format=duration:stream=index,codec_name,codec_type,channels:stream_tags=language,title"
    )
    flags = ["-v", "error", "-show_entries", entries, "-of", "json"]
    command = ["ffprobe", *flags, url]
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=timeout, check=True)
    except FileNotFoundError as exc:
        raise InfraError("ffprobe не установлен") from exc
    except subprocess.TimeoutExpired as exc:
        raise InfraError("ffprobe не дождался потока") from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"ffprobe не прочитал поток: {exc.stderr.strip()[:120]}") from exc
    try:
        payload: Any = json.loads(done.stdout)
    except ValueError as exc:
        raise InfraError("ffprobe вернул не JSON") from exc
    if not isinstance(payload, dict):
        raise InfraError("ffprobe вернул не тот JSON")

    fmt = payload.get("format")
    duration = float((fmt or {}).get("duration") or 0.0) if isinstance(fmt, dict) else 0.0
    raw = payload.get("streams")
    streams = [s for s in raw if isinstance(s, dict)] if isinstance(raw, list) else []
    audio = [s for s in streams if s.get("codec_type") == "audio"]
    video = [_opt_str(s.get("codec_name")) for s in streams if s.get("codec_type") == "video"]
    return Media(
        duration=duration,
        tracks=tuple(_track(i, s) for i, s in enumerate(audio)),
        video=video[0] if video else None,
    )


def _track(index: int, stream: dict[str, Any]) -> AudioTrack:
    raw = stream.get("tags")
    tags: dict[str, Any] = raw if isinstance(raw, dict) else {}
    return AudioTrack(
        index=index,
        language=_opt_str(tags.get("language")),
        title=_opt_str(tags.get("title")),
        codec=_opt_str(stream.get("codec_name")),
        channels=int(stream.get("channels") or 0),
    )


def pick_video_file(files: list[TorrFile]) -> TorrFile:
    """Самый крупный видеофайл раздачи, он же фильм (§2.4); образ диска — :class:`InfraError`."""
    videos = [f for f in files if f.name.lower().endswith(_VIDEO_EXT)]
    if not videos:
        raise InfraError(
            "в раздаче нет отдельного видеофайла (похоже на образ диска) — "
            "возьми другой релиз: cast <запрос> --release N"
        )
    return max(videos, key=lambda f: f.size)


def ffmpeg_hls_command(
    source_url: str, audio_index: int, out_dir: str, start_pos: float = 0.0, readrate: float = 1.0
) -> list[str]:
    """Команда ffmpeg для HLS (§3). Перемотка и resume = рестарт с ``-ss``, манифест с нуля.

    ``EXT-X-PLAYLIST-TYPE:EVENT`` обязателен: без него растущий манифест выглядит как
    live, и приёмник по стандарту стартует за три сегмента до конца — то есть с середины
    фильма. С EVENT и ТВ, и ffmpeg начинают с первого сегмента (проверено).
    ``temp_file`` — чтобы наружу не попал недописанный сегмент или манифест.
    """
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if readrate > 0:
        # Темп реального времени: упаковка не должна убегать от приёмника дальше окна
        # сегментов в tmpfs. Первый сегмент при этом готов через ~4 с — это и есть
        # строка «HLS + запуск приёмника 3–5 с» из бюджета §3.1.
        command += ["-readrate", f"{readrate:g}"]
    if start_pos > 0:
        command += ["-ss", f"{start_pos:.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += (
        f"-c:v copy -c:a {AUDIO_CODEC} -ac {AUDIO_CHANNELS} -b:a {AUDIO_BITRATE} "
        f"-f hls -hls_time {HLS_SEGMENT_SECONDS} -hls_list_size 0 -hls_playlist_type event "
        "-hls_segment_type mpegts -hls_flags independent_segments+temp_file"
    ).split()
    command.append(f"{out_dir.rstrip('/')}/index.m3u8")
    return command


def parse_manifest(text: str) -> tuple[list[tuple[str, float]], bool]:
    """Манифест → пары (сегмент, длительность) и признак конца (``#EXT-X-ENDLIST``)."""
    segments: list[tuple[str, float]] = []
    seconds = 0.0
    for raw in text.splitlines():
        line = raw.strip()
        if line.startswith("#EXTINF:"):
            with contextlib.suppress(ValueError):
                seconds = float(line[8:].split(",")[0])
        elif line and not line.startswith("#"):
            segments.append((line, seconds))
    return segments, "#EXT-X-ENDLIST" in text


def hls_dir(path: str) -> Path:
    """Чистый каталог сегментов. Это tmpfs: фильм на диск не пишем (§3, §1)."""
    directory = Path(path)
    directory.mkdir(parents=True, exist_ok=True)
    for junk in directory.glob("index*"):
        junk.unlink(missing_ok=True)
    return directory


@dataclass(slots=True)
class Packer:
    """Живая упаковка потока в HLS: процесс ffmpeg + окно сегментов в tmpfs."""

    proc: subprocess.Popen[bytes]
    out: Path
    #: Сколько сегментов держим; старые удаляются, фильм целиком в RAM не влезет.
    window: int = 45
    log: Any = None
    _running: bool = True

    @classmethod
    def start(cls, command: list[str], out: Path, window: int = 45) -> Packer:
        log = tempfile.TemporaryFile()  # noqa: SIM115 — живёт всё воспроизведение
        try:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        return cls(proc=proc, out=out, window=window, log=log)

    def manifest(self, timeout: float = 30.0) -> Path:
        """Дождаться первого манифеста; смерть ffmpeg по дороге — честная ошибка (§5)."""
        path = self.out / "index.m3u8"
        deadline = time.monotonic() + timeout
        while not path.exists():
            code = self.proc.poll()
            if code is not None:
                raise InfraError(f"упаковка не запустилась: {self.why()}")
            if time.monotonic() >= deadline:
                raise InfraError(f"ffmpeg не отдал манифест за {timeout:.0f} с")
            time.sleep(0.2)
        return path

    def prune(self, played: float = -1.0, keep: float = 60.0) -> None:
        """Удалить куски, которые приёмник уже прошёл (с запасом ``keep`` секунд).

        ⚠️ Окно в штуках — ловушка: длину сегмента задаёт ключевой кадр источника, и на
        «Моане 2» она гуляла от 1.0 до 11.5 с. «45 штук» оказывались то четырьмя минутами,
        то сорока пятью секундами — и куски исчезали у приёмника из-под носа, а ffmpeg
        молча их пропускал. Поэтому режем по времени и только позади приёмника; счёт в
        штуках остаётся запасным вариантом на приёмник, который позицию не отдаёт.
        """
        if played < 0:
            if self.window > 0:
                for old in sorted(self.out.glob("*.ts"), key=_segment_number)[: -self.window]:
                    old.unlink(missing_ok=True)
            return
        edge, end = played - keep, 0.0
        for name, seconds in self.segments():
            end += seconds
            if end >= edge:
                return
            (self.out / name).unlink(missing_ok=True)

    def pace(self, lead: float) -> None:
        """Придержать упаковку, если она ушла от приёмника дальше половины окна: иначе
        сегменты вычищаются у него из-под носа. Пауза сигналом, ffmpeg её переживает.
        """
        limit = self.window * HLS_SEGMENT_SECONDS
        want = self.window <= 0 or lead < limit / 2
        if want is not self._running and self.proc.poll() is None:
            self.proc.send_signal(signal.SIGCONT if want else signal.SIGSTOP)
            self._running = want

    def segments(self) -> list[tuple[str, float]]:
        """Что сейчас в манифесте: пары (сегмент, длительность)."""
        try:
            return parse_manifest((self.out / "index.m3u8").read_text(encoding="utf-8"))[0]
        except OSError:
            return []

    def poll(self) -> int | None:
        return self.proc.poll()

    def why(self) -> str:
        """Последняя внятная строка от ffmpeg — наружу без трейсбеков (§6)."""
        if self.log is None:
            return "нет вывода"
        self.log.seek(0)
        lines = [ln for ln in self.log.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        return lines[-1][:120] if lines else "нет вывода"

    def stop(self) -> None:
        if self.proc.poll() is None:
            if not self._running:
                self.proc.send_signal(signal.SIGCONT)
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
            if self.proc.poll() is None:
                self.proc.kill()
        for junk in self.out.glob("index*"):
            junk.unlink(missing_ok=True)


def _segment_number(path: Path) -> int:
    found = re.search(r"(\d+)\.ts$", path.name)
    return int(found.group(1)) if found else 0


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит; отсутствие юнита ошибкой не считается."""
    subprocess.run(
        ["systemctl", "--user", "stop", unit], capture_output=True, text=True, check=False
    )


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


#: Отдаём ровно то, что производит ffmpeg, и ничего больше: каталог наружу не открыт.
_ASSET_RE: Final = re.compile(r"^index(?:\d+\.ts|\.m3u8)$")
_TYPES: Final = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}
_RANGE_RE: Final = re.compile(r"bytes=(\d*)-(\d*)")


class _Handler(http.server.BaseHTTPRequestHandler):
    """Манифест и сегменты: CORS на всех ответах, Range на сегментах, ноль лишних путей.

    Range обязателен: ресивер Q70D переспрашивает куски диапазонами (грабли kinocast),
    а без ``Access-Control-Allow-Origin: *`` Chromecast молча не играет (§3, §9).
    """

    protocol_version = "HTTP/1.1"
    server_version = "torrcast"
    root: Path = Path()

    def do_GET(self) -> None:
        self._serve(body=True)

    def do_HEAD(self) -> None:
        self._serve(body=False)

    def do_OPTIONS(self) -> None:
        self._head(204, 0, "text/plain")

    def _serve(self, body: bool) -> None:
        name = self.path.split("?")[0].lstrip("/")
        path = self.root / name
        if not _ASSET_RE.fullmatch(name) or not path.is_file():
            self._head(404, 0, "text/plain")
            return
        try:
            data = path.read_bytes()
        except OSError:  # сегмент вычистило окно ровно между проверкой и чтением
            self._head(404, 0, "text/plain")
            return
        ctype, total = _TYPES.get(path.suffix, "application/octet-stream"), len(data)
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
            self.wfile.write(data)

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
        # Манифест дописывается на ходу — кэшировать его приёмнику нельзя.
        self.send_header("Cache-Control", "no-store" if ctype.endswith("mpegurl") else "max-age=60")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


class _TlsServer(http.server.ThreadingHTTPServer):
    daemon_threads = True
    ctx: ssl.SSLContext

    def get_request(self) -> tuple[Any, Any]:
        # Слушающий сокет остаётся обычным TCP, рукопожатие уходит в рабочий поток:
        # иначе один полуоткрытый коннект вешает весь accept (грабли kinocast).
        sock, addr = super().get_request()
        sock.settimeout(60)
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # битое рукопожатие или оборванный приёмник — не наша авария


class HlsServer:
    """https-раздача HLS с самого стенда (§3): в облако поток не уходит.

    Серт и ключ — пути из конфига: на dev это self-signed, на стенде — LE-файлы,
    и подмена сводится к правке пути. Chromecast self-signed молча не принимает,
    поэтому mock проверяет TLS по тому же файлу (§9).
    """

    def __init__(self, root: Path, cert: str, key: str, host: str = "0.0.0.0", port: int = 8443):
        self.root, self.cert, self.key, self.host, self.port = root, cert, key, host, port
        self._server: _TlsServer | None = None

    def start(self) -> None:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        try:
            ctx.load_cert_chain(self.cert, self.key)
        except (OSError, ssl.SSLError) as exc:
            raise InfraError(f"не читается серт {self.cert}: {why(exc)}") from exc
        handler = type("_Bound", (_Handler,), {"root": self.root})
        try:
            server = _TlsServer((self.host, self.port), handler)
        except OSError as exc:
            raise InfraError(f"порт {self.port} занят или недоступен: {why(exc)}") from exc
        server.ctx = ctx
        self._server = server
        threading.Thread(
            target=server.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True
        ).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
