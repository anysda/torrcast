"""TorrServer, ffprobe и упаковка потока в HLS.

Своего CDN-кода нет: раздачу отдаёт TorrServer (кэш в RAM, на диск не пишем),
пакует ffmpeg (§3 ТЗ). Формат для ТВ зафиксирован и вариаций не имеет:
HLS, сегменты MPEG-TS ~4 с, один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Final
from urllib.parse import quote

from torrcast import InfraError

if TYPE_CHECKING:
    import requests

__all__ = [
    "HLS_SEGMENT_SECONDS",
    "AudioTrack",
    "PlaySession",
    "TorrFile",
    "TorrServer",
    "ffmpeg_hls_command",
    "probe_audio_tracks",
]

#: Длительность сегмента HLS, секунды (§3 — зафиксировано, не настраивается).
HLS_SEGMENT_SECONDS: Final = 4
#: Аудио всегда перекодируется: passthrough AC3/DTS запрещён (§3).
AUDIO_CODEC: Final = "aac"
AUDIO_BITRATE: Final = "192k"
AUDIO_CHANNELS: Final = 2

_TIMEOUT: Final = 30.0
_UNIT_NAME: Final = "torrcast-play"


@dataclass(frozen=True, slots=True)
class TorrFile:
    """Файл внутри раздачи."""

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
    """Звуковая дорожка из ffprobe."""

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


@dataclass(frozen=True, slots=True)
class PlaySession:
    """Запущенная упаковка: transient-юнит ffmpeg и его манифест."""

    unit: str
    playlist_url: str
    source_url: str
    audio_index: int
    start_pos: float = 0.0


class TorrServer:
    """Клиент TorrServer: добавить magnet, узнать файлы, получить URL потока."""

    def __init__(self, base_url: str, timeout: float = _TIMEOUT) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self._session: requests.Session | None = None

    def add(self, magnet: str) -> str:
        """Добавить magnet и вернуть его hash.

        Тот же вызов служит прогревом под меню (§3.1): топ-релиз уходит в
        TorrServer, пока пользователь отвечает на вопросы.
        """
        payload = self._post("/torrents", {"action": "add", "link": magnet, "save_to_db": False})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на добавление")
        torrent_hash = str(payload.get("hash", ""))
        if not torrent_hash:
            raise InfraError("TorrServer не отдал hash раздачи")
        return torrent_hash

    def files(self, torrent_hash: str) -> list[TorrFile]:
        """Список файлов раздачи — из него строится список серий."""
        payload = self._post("/torrents", {"action": "get", "hash": torrent_hash})
        if not isinstance(payload, dict):
            raise InfraError("TorrServer вернул неожиданный ответ на список файлов")
        raw_files = payload.get("file_stats") or []
        files: list[TorrFile] = []
        if isinstance(raw_files, list):
            for item in raw_files:
                if isinstance(item, dict):
                    files.append(
                        TorrFile(
                            index=int(item.get("id") or 0),
                            name=str(item.get("path", "")),
                            size=int(item.get("length") or 0),
                        )
                    )
        return files

    def stream_url(self, torrent_hash: str, index: int) -> str:
        """HTTP-URL потока конкретного файла раздачи."""
        return f"{self.base_url}/stream?link={quote(torrent_hash)}&index={index}&play"

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


def probe_audio_tracks(url: str, timeout: float = _TIMEOUT) -> list[AudioTrack]:
    """Прочитать дорожки прямо из HTTP-потока: ffprobe тянет заголовок по Range.

    Качать файл целиком не нужно — это цена меню озвучек (§3).
    """
    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "a",
        "-show_entries",
        "stream=index,codec_name,channels:stream_tags=language,title",
        "-of",
        "json",
        url,
    ]
    try:
        completed = subprocess.run(
            command, capture_output=True, text=True, timeout=timeout, check=True
        )
    except FileNotFoundError as exc:
        raise InfraError("ffprobe не установлен") from exc
    except subprocess.TimeoutExpired as exc:
        raise InfraError("ffprobe не дождался потока") from exc
    except subprocess.CalledProcessError as exc:
        raise InfraError(f"ffprobe не прочитал поток: {exc.stderr.strip()[:120]}") from exc

    try:
        payload: Any = json.loads(completed.stdout)
    except ValueError as exc:
        raise InfraError("ffprobe вернул не JSON") from exc

    streams = payload.get("streams") if isinstance(payload, dict) else None
    tracks: list[AudioTrack] = []
    if isinstance(streams, list):
        for position, item in enumerate(streams):
            if not isinstance(item, dict):
                continue
            raw_tags = item.get("tags")
            tags: dict[str, Any] = raw_tags if isinstance(raw_tags, dict) else {}
            tracks.append(
                AudioTrack(
                    index=position,
                    language=_opt_str(tags.get("language")),
                    title=_opt_str(tags.get("title")),
                    codec=_opt_str(item.get("codec_name")),
                    channels=int(item.get("channels") or 0),
                )
            )
    return tracks


def ffmpeg_hls_command(
    source_url: str, audio_index: int, out_dir: str, start_pos: float = 0.0
) -> list[str]:
    """Собрать команду ffmpeg для упаковки в HLS.

    Перемотка и resume — это рестарт ffmpeg с ``-ss`` (§3): манифест всегда
    «с нуля», позиция задаётся входом.
    """
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if start_pos > 0:
        command += ["-ss", f"{start_pos:.3f}"]
    command += [
        "-i",
        source_url,
        "-map",
        "0:v:0",
        "-map",
        f"0:a:{audio_index}",
        "-c:v",
        "copy",
        "-c:a",
        AUDIO_CODEC,
        "-ac",
        str(AUDIO_CHANNELS),
        "-b:a",
        AUDIO_BITRATE,
        "-f",
        "hls",
        "-hls_time",
        str(HLS_SEGMENT_SECONDS),
        "-hls_list_size",
        "0",
        "-hls_segment_type",
        "mpegts",
        "-hls_flags",
        "independent_segments",
        f"{out_dir.rstrip('/')}/index.m3u8",
    ]
    return command


def start_play_unit(command: list[str], unit: str = _UNIT_NAME) -> str:
    """Запустить упаковку transient-юнитом ``systemd-run``.

    Своих демонов нет: юнит живёт ровно на время воспроизведения, логи уходят
    в journald, ``cast stop`` его гасит (§3).

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
        ["systemctl", "--user", "stop", unit],
        capture_output=True,
        text=True,
        check=False,
    )


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None
