"""TorrServer, ffprobe и упаковка потока в HLS. Своего CDN-кода нет: раздачу отдаёт
TorrServer (кэш в RAM, на диск не пишем), пакует ffmpeg (§3 ТЗ). Формат для ТВ
зафиксирован: HLS, сегменты MPEG-TS ~4 с, один вариант в манифесте, видео ``copy``,
аудио **всегда** в AAC stereo 192k, CORS ``*`` на всех ответах.
"""

from __future__ import annotations

import contextlib
import http.server
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Final
from urllib.parse import quote

from torrcast import InfraError, why
from torrcast.parse import VIDEO_EXT

if TYPE_CHECKING:
    import requests

    from torrcast.state import Config

__all__ = [
    "HLS_SEGMENT_SECONDS",
    "RUNTIME_GUESS",
    "AudioTrack",
    "Feed",
    "HlsServer",
    "Media",
    "Packer",
    "TorrFile",
    "TorrServer",
    "Warmup",
    "bitrate_mbit",
    "ffmpeg_hls_command",
    "forget_playing",
    "hls_base",
    "hls_dir",
    "mark_playing",
    "our_address",
    "parse_manifest",
    "pick_video_file",
    "playing_flag",
    "probe",
    "segment_name",
    "segment_slot",
    "slot_at",
    "slot_time",
    "start_play_unit",
    "stop_play_unit",
    "unit_active",
    "unit_key",
    "unit_why",
    "vod_manifest",
]

#: Длительность сегмента HLS, секунды (§3 — зафиксировано, не настраивается).
HLS_SEGMENT_SECONDS: Final = 4
#: Плейлист самой упаковки. Приёмнику он не отдаётся: тот получает манифест на весь
#: фильм (:func:`vod_manifest`), а этот нужен только ffmpeg'у как выходной файл.
PACK_PLAYLIST: Final = "pack.m3u8"
_SEGMENT_RE: Final = re.compile(r"v(\d+)\.ts")
#: Флажок «на экране картинка»: его кладёт показ, когда приёмник впервые ответил
#: ``PLAYING``, и ждёт CLI. Спросить приёмник из CLI нельзя — сендер к нему ровно один
#: (:mod:`torrcast.cast`), поэтому доказательство картинки передаётся файлом (§4 SPEC-v2).
PLAYING_FLAG: Final = "playing.flag"
#: Аудио всегда перекодируется: passthrough AC3/DTS запрещён (§3).
AUDIO_CODEC: Final = "aac"
AUDIO_BITRATE: Final = "192k"
AUDIO_CHANNELS: Final = 2
#: Типовая длительность до ffprobe (фильм 2 ч, серия 45 мин): только для прикидки битрейта.
RUNTIME_GUESS: Final = {"movie": 7200.0, "tv": 2700.0, "other": 7200.0}

_TIMEOUT: Final = 30.0
_UNIT_NAME: Final = "torrcast-play"
#: Описание юнита несёт ключ показа — по нему ``status`` знает, что играет (§2.5).
_UNIT_TAG: Final = "torrcast: "
#: Что пробрасывается в юнит: без этого показ уедет на прод-пути вместо dev-овских.
_PASS_ENV: Final = ("TORRCAST_CONFIG", "TORRCAST_STATE", "TORRCAST_TRACE")


def bitrate_mbit(size: int, duration: float) -> float:
    """Средний битрейт раздачи, Мбит/с — предел декодера Q70D ~20 (§3)."""
    return size * 8 / duration / 1e6 if size > 0 and duration > 0 else 0.0


@dataclass(frozen=True, slots=True)
class TorrFile:
    index: int
    name: str
    size: int = 0

    @property
    def base(self) -> str:
        """Имя без пути: сезон живёт в каталоге, номер серии — в имени файла (§2.4)."""
        return self.name.replace("\\", "/").rsplit("/", 1)[-1]


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
    #: Высота кадра из потока. Имя раздачи о качестве тоже молчит через раз, а сказать
    #: человеку «1080p» вместо «?» мы обязаны из того же ffprobe, что уже прочитан.
    height: int = 0

    @property
    def quality(self) -> str:
        """Качество словами: ``1080p``; ноль высоты — честный ``?``."""
        return f"{self.height}p" if self.height else "?"

    @property
    def video_warning(self) -> str:
        """Пустая строка, если ресиверу это точно по зубам (§9: HEVC и экзотика)."""
        if self.video in (None, "h264"):
            return ""
        return f"внимание: видео {self.video} — ресивер может не взять, а мы не перекодируем"

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
        "format=duration:"
        "stream=index,codec_name,codec_type,channels,height:stream_tags=language,title"
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
    video = [s for s in streams if s.get("codec_type") == "video"]
    return Media(
        duration=duration,
        tracks=tuple(_track(i, s) for i, s in enumerate(audio)),
        video=_opt_str(video[0].get("codec_name")) if video else None,
        height=int(video[0].get("height") or 0) if video else 0,
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
    videos = [f for f in files if f.name.lower().endswith(VIDEO_EXT)]
    if not videos:
        raise InfraError(
            "в раздаче нет отдельного видеофайла (похоже на образ диска) — "
            "возьми другой релиз: cast <запрос> --release N"
        )
    return max(videos, key=lambda f: f.size)


def slot_at(seconds: float) -> int:
    """Номер сегмента сетки, в который попадает секунда фильма."""
    return max(0, int(seconds // HLS_SEGMENT_SECONDS))


def slot_time(slot: int) -> float:
    """Секунда фильма, с которой начинается сегмент сетки."""
    return slot * float(HLS_SEGMENT_SECONDS)


def segment_name(slot: int) -> str:
    """Имя файла сегмента. Имя = место в фильме, а не номер по порядку упаковки — это и
    делает возможным манифест на весь фильм при упаковке по требованию (§2.1 SPEC-v2).
    """
    return f"v{slot}.ts"


def segment_slot(name: str) -> int:
    """Слот по имени файла; ``-1`` — имя не наше."""
    found = _SEGMENT_RE.fullmatch(name)
    return int(found.group(1)) if found else -1


def vod_manifest(duration: float) -> str:
    """Манифест VOD на **весь фильм**: сетка по :data:`HLS_SEGMENT_SECONDS` и ``ENDLIST``.

    Это и есть ответ на §2.1 SPEC-v2. Приёмнику неоткуда узнать длительность, кроме
    манифеста: у скользящего live-плейлиста её нет вовсе, поэтому ТВ считал показ эфиром
    и не давал ни таймлайна, ни перемотки. Здесь длительность — сумма ``EXTINF``, то есть
    ровно длина фильма, и перемотка пультом разрешена в любую его точку.

    Манифест **статический**: он не зависит от того, что упаковано прямо сейчас, и
    перечисляет сегменты, которых на диске ещё нет. Целый фильм в tmpfs не влезает — но
    приёмнику и не нужен файл раньше, чем он его попросит: за это отвечает :class:`Feed`,
    которая на запрос неупакованного места перезапускает упаковку оттуда.

    Проверено на живом Q70D 05-08-2026: ``duration`` в MEDIA_STATUS = длине манифеста,
    ``seek`` в произвольную точку отрабатывает за доли секунды и показ продолжается.
    """
    whole = int(duration // HLS_SEGMENT_SECONDS)
    rest = duration - whole * HLS_SEGMENT_SECONDS
    lines = [
        "#EXTM3U",
        "#EXT-X-VERSION:3",
        f"#EXT-X-TARGETDURATION:{HLS_SEGMENT_SECONDS}",
        "#EXT-X-MEDIA-SEQUENCE:0",
        "#EXT-X-PLAYLIST-TYPE:VOD",
    ]
    for slot in range(whole):
        lines += [f"#EXTINF:{float(HLS_SEGMENT_SECONDS):.6f},", segment_name(slot)]
    if rest >= 0.05:  # хвост короче сегмента: без него длительность врала бы на эти секунды
        lines += [f"#EXTINF:{rest:.6f},", segment_name(whole)]
    lines.append("#EXT-X-ENDLIST")
    return "\n".join(lines) + "\n"


def ffmpeg_hls_command(
    source_url: str,
    audio_index: int,
    out_dir: str,
    start_slot: int = 0,
    readrate: float = 1.0,
    burst: float = 0.0,
) -> list[str]:
    """Команда ffmpeg для HLS (§3). Пакует с сегмента ``start_slot`` и кладёт куски под
    именами их мест в фильме — так упакованное ложится в статический манифест (§2.1).

    Два флага держат сетку:

    * ``-copyts`` — временные метки остаются исходными, то есть абсолютным временем
      фильма. Без него ffmpeg сбрасывает их в ноль на каждом ``-ss``, и приёмник после
      перепаковки показывал бы позицию от начала куска, а не от начала фильма.
    * ``split_by_time`` — резать строго по 4 с, а не по ключевым кадрам. Ключевые кадры
      источника ложатся как попало (на «Моане 2» от 1.0 до 11.5 с), и сегменты
      «сколько дал GOP» разъезжаются с сеткой манифеста тем сильнее, чем дальше от
      начала. С ним длительность сегмента ровно 4.000 с, и место сегмента в фильме
      считается арифметикой, а не гаданием. Плата — сегмент начинается не с ключевого
      кадра, поэтому ``independent_segments`` больше не ставится: это было бы враньё.

    ⚠️ ``-ss`` перед ``-i`` уводит ffmpeg на ключевой кадр **не позже** запрошенного
    места, поэтому упаковка начинается на ``δ`` секунд раньше сетки (δ ≤ длины GOP).
    Ошибка постоянная: она не копится, потому что дальше режет таймер, а не GOP.

    Темп упаковки (§6 SPEC-v2) держится **одним ffmpeg'ом и без пауз процесса**:

    * ``-readrate 1`` — читать вход со скоростью реального времени. Придержать упаковку
      сигналом (SIGSTOP) больше не нужно: она сама не убегает дальше ``burst``.
    * ``-readrate_initial_burst`` (ffmpeg ≥ 6.1) — первые ``burst`` секунд читаются на
      полной скорости. Без него ``readrate 1`` дважды вреден: приёмник идёт вровень с
      упаковкой и буферится на каждом стыке, а после перемотки ему разом нужны шесть
      сегментов (замерено на Q70D: v50…v55 за одну секунду).

    Отставание ffmpeg наверстывает сам: его планка — ``wallclock * readrate + burst``, и
    пока текущий dts ниже планки, он читает на полной скорости (``readrate_sleep`` в
    fftools). То есть просадка роя лечится без нашего участия, а запас впереди приёмника
    остаётся ограниченным ``burst`` — ровно поэтому tmpfs не растёт без предела.
    """
    command = ["ffmpeg", "-hide_banner", "-loglevel", "warning"]
    if readrate > 0:
        command += ["-readrate", f"{readrate:g}"]
        if burst > 0:
            command += ["-readrate_initial_burst", f"{burst:g}"]
    command += ["-copyts"]
    if start_slot > 0:
        command += ["-ss", f"{slot_time(start_slot):.3f}"]
    command += ["-i", source_url, "-map", "0:v:0", "-map", f"0:a:{audio_index}"]
    command += (
        f"-c:v copy -c:a {AUDIO_CODEC} -ac {AUDIO_CHANNELS} -b:a {AUDIO_BITRATE} "
        f"-f hls -hls_time {HLS_SEGMENT_SECONDS} -hls_list_size 0 "
        "-hls_segment_type mpegts -hls_flags split_by_time+temp_file "
        f"-start_number {start_slot} -hls_segment_filename {out_dir.rstrip('/')}/v%d.ts"
    ).split()
    command.append(f"{out_dir.rstrip('/')}/{PACK_PLAYLIST}")
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
    for junk in (*directory.glob("v*.ts"), *directory.glob("*.m3u8")):
        junk.unlink(missing_ok=True)
    forget_playing(directory)  # флажок прошлого показа картинку нового не доказывает
    return directory


def playing_flag(out: Path) -> Path:
    """Путь флажка «картинка на экране» (:data:`PLAYING_FLAG`)."""
    return out / PLAYING_FLAG


def mark_playing(out: Path) -> None:
    """Показ увидел ``PLAYING``: с этой секунды на экране есть изображение (§4 SPEC-v2)."""
    with contextlib.suppress(OSError):
        playing_flag(out).touch()


def forget_playing(out: Path) -> None:
    """Убрать флажок: следующий показ обязан доказать картинку заново."""
    with contextlib.suppress(OSError):
        playing_flag(out).unlink(missing_ok=True)


@dataclass(slots=True)
class Packer:
    """Один прогон упаковки: процесс ffmpeg, который пакует фильм с сегмента ``first``."""

    proc: subprocess.Popen[bytes]
    out: Path
    #: С какого сегмента сетки начат этот прогон: всё, что раньше, паковал не он.
    first: int = 0
    log: Any = None
    #: Упаковку погасили намеренно (пауза на пульте) — смерть процесса не авария.
    halted: bool = False

    @classmethod
    def start(cls, command: list[str], out: Path, first: int = 0) -> Packer:
        log = tempfile.TemporaryFile()  # noqa: SIM115 — живёт всё воспроизведение
        try:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=log)
        except FileNotFoundError as exc:
            raise InfraError("ffmpeg не установлен") from exc
        return cls(proc=proc, out=out, first=first, log=log)

    def frontier(self) -> int:
        """Последний готовый сегмент этого прогона; ``first - 1`` — ещё ничего не готово.

        Считается по файлам, а не по плейлисту ffmpeg: файл появляется атомарно
        (``temp_file`` пишет рядом и переименовывает), значит существование = готовность.
        """
        slots = [s for s in map(segment_slot, _names(self.out)) if s >= self.first]
        return max(slots, default=self.first - 1)

    def halt(self) -> None:
        """Погасить упаковку, **не трогая уже упакованное**: приёмник на паузе, и копить
        сегменты в tmpfs незачем. Возобновление — новый прогон (:meth:`Feed.segment`).

        Раньше на этом месте стояла пауза сигналом (SIGSTOP). Она и оказалась классом
        проблемы §6 SPEC-v2: манифест замирает, а приёмник намертво виснет в BUFFERING —
        держит коннект и не запрашивает ничего. Поэтому процесс именно завершается.
        """
        self.halted = True
        self.stop(keep_files=True)

    def poll(self) -> int | None:
        return self.proc.poll()

    def why(self) -> str:
        """Последняя внятная строка от ffmpeg — наружу без трейсбеков (§6)."""
        if self.log is None:
            return "нет вывода"
        self.log.seek(0)
        lines = [ln for ln in self.log.read().decode("utf-8", "replace").splitlines() if ln.strip()]
        return lines[-1][:120] if lines else "нет вывода"

    def stop(self, keep_files: bool = False) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            with contextlib.suppress(subprocess.TimeoutExpired):
                self.proc.wait(timeout=5)
            if self.proc.poll() is None:
                self.proc.kill()
        if not keep_files:
            for junk in (*_paths(self.out), self.out / PACK_PLAYLIST):
                junk.unlink(missing_ok=True)


def _names(out: Path) -> list[str]:
    return [path.name for path in out.glob("v*.ts")]


def _paths(out: Path) -> list[Path]:
    return list(out.glob("v*.ts"))


@dataclass(slots=True)
class Feed:
    """Упаковка по требованию: манифест обещает весь фильм, в tmpfs лежит окно (§2.1).

    Это ответ на железное ограничение: приёмнику нужен манифест на всю длительность,
    иначе у показа нет ни таймлайна, ни перемотки, — а целый фильм ни в RAM, ни на диск
    стенда не влезает. Развязка в том, что манифест и файлы живут порознь:

    * :func:`vod_manifest` перечисляет **все** сегменты фильма и не меняется никогда;
    * файлы под этими именами появляются только там, где приёмник смотрит прямо сейчас;
    * запрос сегмента, которого нет, — это и есть перемотка. Показ не отвечает 404
      (после него ресивер капризничает минутами), а перезапускает упаковку с нужного
      места и отдаёт кусок, как только он готов.

    Отсюда же берётся честная позиция: имя сегмента = его место в фильме, ``-copyts``
    держит исходные метки времени, и приёмник считает время от начала фильма, а не от
    начала куска. Никаких смещений показу пересчитывать не нужно.
    """

    source: str
    audio: int
    out: Path
    duration: float
    readrate: float = 1.0
    burst: float = 60.0
    #: Сколько секунд позади показа держим сегменты — глубина «бесплатной» перемотки назад.
    keep: float = 120.0
    #: Запрос дальше упакованного края больше чем на столько секунд — это перемотка, а не
    #: обычный ход показа. Меньше 30 с брать нельзя: после ``seek`` живой Q70D просит
    #: шесть сегментов разом (замерено), и каждый из них не должен считаться перемоткой.
    ahead: float = 40.0
    #: Сколько держим запрос приёмника, пока упаковка догоняет. Это лучше 404: ресивер,
    #: поймавший 404, отказывается брать LOAD ещё пару минут (замерено 05-08-2026).
    wait: float = 30.0
    #: Сколько раз упаковка успела оборваться сама. Пережить обрыв она обязана: TorrServer
    #: под просевшим роем закрывает вход, и ffmpeg честно умирает — а показу это уже не
    #: авария, потому что паковать заново он умеет с любого места. Но молча повторять до
    #: бесконечности нельзя: битый источник крутил бы этот круг вечно.
    limit: int = 3
    packer: Packer | None = None
    lock: Any = field(default_factory=threading.Lock)
    #: Когда последний раз перезапускали упаковку: защита от лавины на префетче.
    restarted: float = 0.0
    crashes: int = 0
    fatal: str = ""
    log: Any = None

    def manifest(self) -> bytes:
        return vod_manifest(self.duration).encode("utf-8")

    def segment(self, slot: int) -> Path | None:
        """Файл сегмента ``slot``; ``None`` — его не будет (за концом фильма или не успели).

        Зовётся из потоков раздачи, поэтому решение о перезапуске упаковки принимается
        под замком: после перемотки приёмник просит несколько сегментов одновременно, и
        перезапустить упаковку должен ровно первый из них.
        """
        path = self.out / segment_name(slot)
        deadline = time.monotonic() + self.wait
        while True:
            if path.exists():
                return path
            with self.lock:
                self._steer(slot)
            if path.exists():
                return path
            if time.monotonic() >= deadline:
                return None
            time.sleep(0.2)

    def _steer(self, slot: int) -> None:
        """Решить, что делать с упаковкой ради сегмента ``slot``: ждать или начать заново."""
        packer = self.packer
        if packer is not None and not packer.halted:
            code, frontier = packer.poll(), packer.frontier()
            if code == 0 and slot > frontier:
                return  # упаковка честно дошла до конца входа — файла не будет
            if code is None and packer.first <= slot <= frontier + slot_at(self.ahead) + 1:
                return  # обычный ход показа: кусок вот-вот допакуется
            if code not in (None, 0) and not self._survive(packer):
                return
        if self.fatal or time.monotonic() - self.restarted < 2.0:
            return  # либо уже сдались, либо соседний запрос перезапустил — не толкаемся
        self.restarted = time.monotonic()
        self.restart(slot)

    def _survive(self, packer: Packer) -> bool:
        """Упаковка оборвалась сама: пробуем ещё или сдаёмся честной ошибкой."""
        self.crashes += 1
        # Убитый сигналом ffmpeg сказать ничего не успевает — не выдумываем за него.
        code = packer.poll() or 0
        why = f"убит сигналом {-code}" if code < 0 else packer.why()
        if self.crashes > self.limit:
            self.fatal = why
            return False
        self._say(f"упаковка оборвалась ({why}) — начинаю заново, попытка {self.crashes}")
        return True

    def restart(self, slot: int) -> None:
        """Начать упаковку с сегмента ``slot``: перемотка, возврат с паузы или старт показа.

        Всё, что лежит от этого места и дальше, — от прошлого прогона и о новом месте
        ничего не знает, поэтому убирается. Позади оставляем: там окно перемотки назад.
        """
        if self.packer is not None:
            self.packer.stop(keep_files=True)
        for path in _paths(self.out):
            if segment_slot(path.name) >= slot:
                path.unlink(missing_ok=True)
        (self.out / PACK_PLAYLIST).unlink(missing_ok=True)
        command = ffmpeg_hls_command(
            self.source, self.audio, str(self.out), slot, self.readrate, self.burst
        )
        self.restarted = time.monotonic()
        self.packer = Packer.start(command, self.out, slot)
        self._say(f"упаковка с {slot_time(slot):.0f} с")

    def prune(self, played: float) -> None:
        """Убрать из tmpfs то, что приёмник давно прошёл. Окно = ``keep`` секунд позади
        показа: глубже — уже перемотка, и она честно перепакует поток.
        """
        edge = slot_at(played - self.keep)
        if edge <= 0:
            return
        for path in _paths(self.out):
            if 0 <= segment_slot(path.name) < edge:
                path.unlink(missing_ok=True)

    def front(self) -> float:
        """Докуда упаковано, секунды от начала фильма: конец последнего готового сегмента.

        Разница между этим числом и позицией приёмника — весь запас показа. Он и есть
        предмет §6 SPEC-v2: пока запас положителен, приёмнику всегда есть что взять, а
        как только он сходит в ноль — приёмник встаёт в BUFFERING.
        """
        packer = self.packer
        return 0.0 if packer is None else slot_time(packer.frontier() + 1)

    def weight(self) -> int:
        """Сколько байт сегментов лежит в tmpfs прямо сейчас (§6: рост без предела —
        недопустим, а это единственный способ увидеть пик своими глазами)."""
        total = 0
        for path in _paths(self.out):
            with contextlib.suppress(OSError):  # вычистило окном прямо сейчас
                total += path.stat().st_size
        return total

    def trouble(self) -> str:
        """Почему показ дальше не идёт, если не идёт; пусто — всё в порядке.

        Мёртвый ffmpeg сам по себе поводом остановить показ не является: код 0 — это
        конец входа (остаток фильма уже в tmpfs), а обрыв лечится следующей упаковкой.
        Ошибкой это становится, только когда обрывы пошли подряд (:attr:`limit`).
        """
        return self.fatal

    def halted(self) -> bool:
        return self.packer is not None and self.packer.halted

    def halt(self) -> None:
        if self.packer is not None:
            self.packer.halt()

    def stop(self) -> None:
        if self.packer is not None:
            self.packer.stop()
        for junk in (*_paths(self.out), self.out / PACK_PLAYLIST):
            junk.unlink(missing_ok=True)

    def _say(self, text: str) -> None:
        if self.log is not None:
            self.log(text)


def _scope() -> list[str]:
    """Юнит системный, когда мы root (так на стенде из ``install.sh``), иначе
    пользовательский (так на dev). Постоянных юнитов у нас нет ни там, ни там — только
    transient на время показа (§3).
    """
    return [] if os.geteuid() == 0 else ["--user"]


def _systemd(tool: str, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [tool, *_scope(), *args], capture_output=True, text=True, check=False, timeout=60
    )


def start_play_unit(key: str, unit: str = _UNIT_NAME) -> None:
    """Запустить показ в transient-юните: ``cast`` завершился — показ продолжается,
    логи бесплатно в journald (§3). Переменные окружения проброшены, иначе юнит возьмёт
    прод-пути конфига и состояния вместо dev-овских.
    """
    stop_play_unit(unit)
    env = [f"--setenv={n}={os.environ[n]}" for n in _PASS_ENV if n in os.environ]
    done = _systemd(
        "systemd-run", f"--unit={unit}", "--collect", "--quiet",
        f"--description={_UNIT_TAG}{key}", *env,
        sys.executable, "-m", "torrcast.cli", "--play-key", key,
    )  # fmt: skip
    if done.returncode != 0:
        raise InfraError(f"не запустился юнит {unit}: {done.stderr.strip()[:120] or 'systemd-run'}")


def stop_play_unit(unit: str = _UNIT_NAME) -> None:
    """Погасить transient-юнит и дождаться его смерти: по SIGTERM сторож дописывает
    позицию в state. Отсутствие юнита ошибкой не считается.
    """
    _systemd("systemctl", "stop", unit)


def unit_active(unit: str = _UNIT_NAME) -> bool:
    """Идёт ли показ прямо сейчас."""
    return _systemd("systemctl", "is-active", unit).stdout.strip() == "active"


def unit_key(unit: str = _UNIT_NAME) -> str:
    """Ключ состояния играющего показа — из ``--description`` юнита. Свежайшая запись в
    state для этого не годится: рядом мог писать другой ход, и ``status`` соврал бы.
    """
    found = _systemd("systemctl", "show", unit, "-p", "Description", "--value").stdout.strip()
    return found[len(_UNIT_TAG) :].strip() if found.startswith(_UNIT_TAG) else ""


def unit_why(unit: str = _UNIT_NAME) -> str:
    """Последняя внятная строка юнита из journald — наружу без трейсбеков (§6)."""
    out = _systemd("journalctl", "-u", unit, "-n", "10", "--no-pager", "-o", "cat").stdout
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return lines[-1][:160] if lines else "в журнале пусто"


def _opt_str(value: Any) -> str | None:
    return str(value) if value not in (None, "") else None


#: Отдаём ровно манифест и сегменты сетки, и ничего больше: каталог наружу не открыт.
_ASSET_RE: Final = re.compile(r"^(?:v\d+\.ts|index\.m3u8)$")
_TYPES: Final = {".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t"}
_RANGE_RE: Final = re.compile(r"bytes=(\d*)-(\d*)")
#: ``TORRCAST_TRACE=1`` — раздача пишет в журнал каждый запрос приёмника (:meth:`_Handler._trace`).
TRACE: Final = bool(os.environ.get("TORRCAST_TRACE"))


class _Handler(http.server.BaseHTTPRequestHandler):
    """Манифест и сегменты: CORS на всех ответах, Range на сегментах, ноль лишних путей.

    Range обязателен: ресивер Q70D переспрашивает куски диапазонами (грабли kinocast),
    а без ``Access-Control-Allow-Origin: *`` Chromecast молча не играет (§3, §9).

    Манифест берётся не с диска, а у :class:`Feed`: он описывает весь фильм, а не то,
    что успело упаковаться (§2.1 SPEC-v2). Запрос сегмента тоже уходит в ``Feed`` —
    именно там запрос неупакованного места превращается в перемотку.
    """

    protocol_version = "HTTP/1.1"
    server_version = "torrcast"
    root: Path = Path()
    feed: ClassVar[Feed | None] = None

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
        self._trace(name, began, f"{len(data) / 1e6:.1f} МБ")
        suffix = ".m3u8" if name.endswith(".m3u8") else ".ts"
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
            self.wfile.write(data)

    def _read(self, name: str) -> bytes | None:
        """Тело ответа: манифест на весь фильм или сегмент, дождавшись упаковки."""
        if name.endswith(".m3u8"):
            return self.feed.manifest() if self.feed is not None else None
        path = self.root / name
        if self.feed is not None:
            found = self.feed.segment(segment_slot(name))
            if found is None:
                return None
            path = found
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
        # (перемотка назад глубже окна, §6 SPEC-v2) под теми же именами сегментов лежит
        # уже другое место фильма — кэш приёмника показал бы старое.
        self.send_header("Cache-Control", "no-store")
        for key, value in extra:
            self.send_header(key, value)
        self.end_headers()

    def _trace(self, name: str, began: float, got: str) -> None:
        """Что попросил приёмник, сколько ждал ответа и что получил (``TORRCAST_TRACE=1``).

        Без этого §6 SPEC-v2 не измерить: подвис приёмника снаружи выглядит одинаково и
        когда он ждёт нас, и когда он перестал спрашивать вовсе, — а лечится это по-разному.
        """
        if not TRACE:
            return
        span = self.headers.get("Range", "")
        print(
            f"запрос {name}{' ' + span if span else ''} · ждал {time.monotonic() - began:.1f} с"
            f" · {got}",
            flush=True,
        )

    def log_message(self, fmt: str, *args: Any) -> None:
        pass


class _Server(http.server.ThreadingHTTPServer):
    daemon_threads = True
    #: Контекст TLS или ``None`` — тогда раздача идёт голым http (дефолт, §5 SPEC-v2).
    ctx: ssl.SSLContext | None = None

    def get_request(self) -> tuple[Any, Any]:
        # Слушающий сокет остаётся обычным TCP, рукопожатие уходит в рабочий поток:
        # иначе один полуоткрытый коннект вешает весь accept (грабли kinocast).
        sock, addr = super().get_request()
        sock.settimeout(60)
        if self.ctx is None:
            return sock, addr
        return self.ctx.wrap_socket(sock, server_side=True, do_handshake_on_connect=False), addr

    def handle_error(self, request: Any, client_address: Any) -> None:
        pass  # битое рукопожатие или оборванный приёмник — не наша авария


class HlsServer:
    """Раздача HLS с самого стенда (§3): в облако поток не уходит.

    Дефолт — голый http (§5 SPEC-v2): ТВ ходит по IP, ни серта, ни имени, ни DNS в пути
    показа нет. ``tls=True`` включает прежнюю https-раздачу — код жив и работает, но
    требует серта, которому доверяет ТВ (Chromecast self-signed молча не принимает, §9).
    """

    def __init__(
        self,
        root: Path,
        cert: str = "",
        key: str = "",
        host: str = "0.0.0.0",
        port: int = 8080,
        tls: bool = False,
        feed: Feed | None = None,
    ):
        self.root, self.cert, self.key, self.host, self.port = root, cert, key, host, port
        self.tls = tls
        self.feed = feed
        self._server: _Server | None = None

    def start(self) -> None:
        ctx = None
        if self.tls:
            ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            try:
                ctx.load_cert_chain(self.cert, self.key)
            except (OSError, ssl.SSLError) as exc:
                raise InfraError(f"не читается серт {self.cert}: {why(exc)}") from exc
        handler = type("_Bound", (_Handler,), {"root": self.root, "feed": self.feed})
        try:
            server = _Server((self.host, self.port), handler)
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


def our_address(tv: str) -> str:
    """Наш адрес **с той стороны, с которой нас видит ТВ**, или пусто, если маршрута нет.

    У стенда две ноги: ``192.168.1.62`` в домашней сети и ``192.168.100.62`` в сегменте
    телевизора. Ядро выбирает исходящий адрес по маршруту, поэтому спрашиваем его же:
    сокет никуда не подключается по-настоящему (UDP, ни одного пакета), но имя ему
    присваивается ровно то, которое ТВ увидит источником. Так поток идёт в одном L2, а
    не лишним хопом через SNAT маршрутизатора.
    """
    if not tv:
        return ""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect((tv, 8009))
        return str(sock.getsockname()[0])
    except OSError:
        return ""
    finally:
        sock.close()


def hls_base(config: Config) -> str:
    """База URL, под которой ТВ забирает манифест и сегменты (§5 SPEC-v2).

    Имени здесь нет и быть не должно: адрес собирается из транспорта, нашей ноги со
    стороны ТВ и порта — DNS в пути показа не участвует. ``hls_base_url`` в конфиге,
    если он задан, перебивает всё: это запасной выход на случай, когда прямой путь
    почему-то не работает.
    """
    if config.hls_base_url:
        return config.hls_base_url.rstrip("/")
    host = our_address(config.tv or "")
    if not host:
        raise InfraError(f"не вижу маршрута до ТВ {config.tv or '(адрес не задан)'}")
    return f"{config.transport}://{host}:{config.hls_port}"
