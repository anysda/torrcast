"""Конфиг и состояние просмотра: ``/etc/torrcast/config.json`` (обязателен только
адрес ТВ) и ``/var/lib/torrcast/state.json`` (запись атомарная: tmp + rename).
Обе точки переопределяются переменными окружения ``TORRCAST_STATE`` и
``TORRCAST_CONFIG`` — это нужно тестам и локальному запуску.
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict, dataclass
from importlib import import_module
from pathlib import Path
from typing import Any

from torrcast.domain.config import Config
from torrcast.domain.entry import Entry
from torrcast.domain.watch_state import WatchState

_package = import_module("torrcast")
TorrcastError = _package.TorrcastError

__all__ = [
    "Config",
    "Entry",
    "State",
    "config_keys",
    "config_path",
    "load_config",
    "save_config",
    "state_path",
]


DEFAULT_STATE_PATH = Path("/var/lib/torrcast/state.json")
DEFAULT_CONFIG_PATH = Path("/etc/torrcast/config.json")


def state_path() -> Path:
    """Путь к файлу состояния с учётом ``TORRCAST_STATE``."""
    return Path(os.environ.get("TORRCAST_STATE") or DEFAULT_STATE_PATH)


def config_path() -> Path:
    """Путь к конфигу с учётом ``TORRCAST_CONFIG``."""
    return Path(os.environ.get("TORRCAST_CONFIG") or DEFAULT_CONFIG_PATH)


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


def config_keys() -> frozenset[str]:
    """Ключи, действительно написанные в JSON, в отличие от умолчаний :class:`Config`.

    Вызывается после :func:`load_config`, поэтому повторная короткая читка не вводит
    второй способ разбирать настройки. Она нужна следу: одинаковое число может прийти
    из файла стенда или из умолчания, а задним числом по одному значению их не отличить.
    """
    path = config_path()
    if not path.exists():
        return frozenset()
    try:
        raw: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return frozenset()
    if not isinstance(raw, dict):
        return frozenset()
    return frozenset(key for key in raw if key in Config.__dataclass_fields__)


def save_config(config: Config) -> None:
    """Записать конфиг атомарно, создав каталог при необходимости."""
    _write_atomic(config_path(), asdict(config))


@dataclass(slots=True)
class State(WatchState):
    """Состояние просмотра, прочитанное из файла и в файл же записываемое.

    Правила «что спрашивают у состояния» - в :class:`~torrcast.domain.watch_state.
    WatchState`; здесь остаётся ровно файл: чтение, атомарная запись и путь к нему.
    """

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
