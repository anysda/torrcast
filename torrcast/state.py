"""Конфиг и состояние просмотра: ``/etc/torrcast/config.json`` (обязателен только
адрес ТВ) и ``/var/lib/torrcast/state.json`` (структура записи — §4 ТЗ, запись
атомарная: tmp + rename). Обе точки переопределяются переменными окружения
``TORRCAST_STATE`` и ``TORRCAST_CONFIG`` — это нужно тестам и стенду.
"""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass, field, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Literal

from torrcast import TorrcastError

__all__ = ["Config", "Entry", "State", "config_path", "load_config", "save_config", "state_path"]

Kind = Literal["movie", "tv"]

DEFAULT_STATE_PATH = Path("/var/lib/torrcast/state.json")
DEFAULT_CONFIG_PATH = Path("/etc/torrcast/config.json")

#: Доля длительности, после которой позиция считается «досмотрено» (§2.4).
WATCHED_RATIO = 0.95


def state_path() -> Path:
    """Путь к файлу состояния с учётом ``TORRCAST_STATE``."""
    return Path(os.environ.get("TORRCAST_STATE") or DEFAULT_STATE_PATH)


def config_path() -> Path:
    """Путь к конфигу с учётом ``TORRCAST_CONFIG``."""
    return Path(os.environ.get("TORRCAST_CONFIG") or DEFAULT_CONFIG_PATH)


@dataclass(slots=True)
class Config:
    """Настройки. Обязателен только ``tv``; остальное имеет рабочие дефолты."""

    tv: str | None = None
    receiver: Literal["chromecast", "mock"] = "chromecast"
    torrserver_url: str = "http://127.0.0.1:8090"
    prowlarr_url: str = "http://127.0.0.1:9696"
    prowlarr_apikey: str = ""
    #: Базовый https-URL, под которым ТВ забирает HLS (§3).
    hls_base_url: str = "https://torrcast.anysda.space"
    hls_port: int = 8443
    #: Серт и ключ: на стенде тут окажутся файлы LE — подмена сводится к правке пути (§9).
    hls_cert: str = "/etc/torrcast/tls/torrcast.crt"
    hls_key: str = "/etc/torrcast/tls/torrcast.key"
    #: Сегменты живут в tmpfs — фильм на диск не пишем (§3); окно в сегментах по 4 с.
    hls_dir: str = "/dev/shm/torrcast"
    hls_window: int = 45
    #: Темп упаковки: 1.0 = реальное время (так живёт ТВ), 0 = без ограничения (приёмка).
    hls_readrate: float = 1.0
    #: Практический потолок битрейта приёмника, Мбит/с (урок Q70D, §3).
    bitrate_warn_mbit: float = 20.0

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Config:
        """Собрать конфиг из словаря, молча игнорируя незнакомые ключи."""
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


def load_config() -> Config:
    """Прочитать конфиг; отсутствующий файл — не ошибка, а дефолты."""
    path = config_path()
    if not path.exists():
        return Config()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise TorrcastError(f"битый конфиг {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise TorrcastError(f"битый конфиг {path}: ожидался объект JSON")
    return Config.from_json(raw)


def save_config(config: Config) -> None:
    """Записать конфиг атомарно, создав каталог при необходимости."""
    _write_atomic(config_path(), asdict(config))


@dataclass(slots=True)
class Entry:
    """Запись состояния: что смотрим, чем и с какого места (§4 ТЗ)."""

    title: str
    magnet: str
    kind: Kind = "movie"
    file_idx: int = 0
    audio: int = 0
    pos: float = 0.0
    dur: float = 0.0
    season: int | None = None
    episode: int | None = None
    updated: str = ""

    @property
    def watched(self) -> bool:
        """Досмотрено ли: позиция ≥ 95 % длительности (§2.4)."""
        return self.dur > 0 and self.pos >= self.dur * WATCHED_RATIO

    def touch(self) -> Entry:
        """Копия записи со свежей меткой времени."""
        return replace(self, updated=datetime.now(UTC).astimezone().isoformat())

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> Entry:
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass(slots=True)
class State:
    """Состояние целиком: ключ ``<тип>:<slug>:<год>`` → :class:`Entry`."""

    entries: dict[str, Entry] = field(default_factory=dict)

    @classmethod
    def load(cls) -> State:
        """Прочитать состояние; отсутствующий или битый файл — пустое состояние."""
        try:
            raw: Any = json.loads(state_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls()
        if not isinstance(raw, dict):
            return cls()
        return cls({str(k): Entry.from_json(v) for k, v in raw.items() if isinstance(v, dict)})

    def save(self) -> None:
        _write_atomic(state_path(), {k: asdict(v) for k, v in self.entries.items()})

    def get(self, key: str) -> Entry | None:
        return self.entries.get(key)

    def put(self, key: str, entry: Entry) -> None:
        """Положить запись, обновив метку времени."""
        self.entries[key] = entry.touch()

    def drop(self, key: str) -> None:
        """Забыть запись (``--new``)."""
        self.entries.pop(key, None)

    def __iter__(self) -> Iterator[tuple[str, Entry]]:
        return iter(self.entries.items())


def _write_atomic(path: Path, payload: dict[str, Any]) -> None:
    """Записать JSON во временный файл рядом и переименовать поверх цели."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
        tmp.replace(path)
    except OSError as exc:
        tmp.unlink(missing_ok=True)
        raise TorrcastError(f"не смог записать {path}: {exc}") from exc
