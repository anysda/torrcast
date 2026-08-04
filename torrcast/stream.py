"""TorrServer, ffprobe и упаковка потока в HLS. Своего CDN-кода нет: раздачу отдаёт
TorrServer (кэш в RAM, на диск не пишем), пакует ffmpeg (§3 ТЗ). Формат для ТВ
зафиксирован: HLS, сегменты MPEG-TS ~4 с, один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

import contextlib
import json
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from torrcast import InfraError

if TYPE_CHECKING:
    import requests

__all__ = [
    "HLS_SEGMENT_SECONDS",
    "RUNTIME_GUESS",
    "AudioTrack",
    "Media",
    "TorrFile",
    "TorrServer",
    "Warmup",
    "bitrate_mbit",
    "ffmpeg_hls_command",
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
    """Что ffprobe вычитал из потока: длительность и звуковые дорожки."""

    duration: float = 0.0
    tracks: tuple[AudioTrack, ...] = ()

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
            raise InfraError(f"TorrServer не отвечает ({self.base_url}): {exc}") from exc
        except ValueError as exc:
            raise InfraError("TorrServer вернул не JSON") from exc


def probe(url: str, timeout: float = 90.0) -> Media:
    """Дорожки и длительность из HTTP-потока, не качая файл: ffprobe берёт заголовок mkv
    запросами Range — это и есть цена меню озвучек (§3).
    """
    entries = "format=duration:stream=index,codec_name,channels:stream_tags=language,title"
    flags = ["-v", "error", "-select_streams", "a", "-show_entries", entries, "-of", "json"]
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
    streams = payload.get("streams")
    audio = [s for s in streams if isinstance(s, dict)] if isinstance(streams, list) else []
    return Media(duration=duration, tracks=tuple(_track(i, s) for i, s in enumerate(audio)))


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
    source_url: str, audio_index: int, out_dir: str, start_pos: float = 0.0
) -> list[str]:
    """Команда ffmpeg для HLS: перемотка и resume = рестарт с ``-ss``, манифест с нуля (§3)."""
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if start_pos > 0:
        command += ["-ss", f"{start_pos:.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += (
        f"-c:v copy -c:a {AUDIO_CODEC} -ac {AUDIO_CHANNELS} -b:a {AUDIO_BITRATE} "
        f"-f hls -hls_time {HLS_SEGMENT_SECONDS} -hls_list_size 0 "
        "-hls_segment_type mpegts -hls_flags independent_segments"
    ).split()
    command.append(f"{out_dir.rstrip('/')}/index.m3u8")
    return command


def start_play_unit(command: list[str], unit: str = _UNIT_NAME) -> str:
    """Упаковка transient-юнитом ``systemd-run``: своих демонов нет, юнит живёт ровно на
    время показа, логи в journald, гасит ``cast stop`` (§3).

    TODO(этап 3): сторож позиции раз в 10 с и автопереход серий.
    """
    full = ["systemd-run", "--user", f"--unit={unit}", "--collect", *command]
    try:
        subprocess.run(full, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise InfraError("systemd-run недоступен") from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"не смог запустить упаковку: {exc.stderr.strip()[:120]}") from exc
    return unit


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит; отсутствие юнита ошибкой не считается."""
    subprocess.run(
        ["systemctl", "--user", "stop", unit], capture_output=True, text=True, check=False
    )


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
