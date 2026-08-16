"""Хранит позиции воспроизведения в прежнем JSON-файле атомарно."""

from __future__ import annotations

import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from torrcast.domain.playback_state import PlaybackState

DEFAULT_STATE_PATH = Path("/var/lib/torrcast/state.json")


class JsonStateStore:
    """Реализация порта состояния без потери соседних полей старого формата."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self._environ = environ if environ is not None else os.environ

    def load(self, key: str) -> PlaybackState | None:
        raw = self._read()
        entry = raw.get(key)
        if not isinstance(entry, dict):
            return None
        position = entry.get("pos", entry.get("position", 0.0))
        try:
            if position is None:
                return None
            return PlaybackState(key=key, position=float(position))
        except (TypeError, ValueError):
            return None

    def save(self, state: PlaybackState) -> None:
        raw = self._read()
        entry = raw.get(state.key)
        if not isinstance(entry, dict):
            entry = {}
        entry["pos"] = state.position
        raw[state.key] = entry
        self._write(raw)

    def _path(self) -> Path:
        return Path(self._environ.get("TORRCAST_STATE") or DEFAULT_STATE_PATH)

    def _read(self) -> dict[str, Any]:
        try:
            raw: Any = json.loads(self._path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def _write(self, payload: dict[str, Any]) -> None:
        path = self._path()
        path.parent.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(dir=path.parent, prefix=f".{path.name}.", suffix=".tmp")
        temporary = Path(name)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(
                    json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
                )
                handle.flush()
                os.fsync(handle.fileno())
            temporary.replace(path)
        except OSError:
            temporary.unlink(missing_ok=True)
            raise
