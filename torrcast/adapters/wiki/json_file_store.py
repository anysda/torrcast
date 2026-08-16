"""Хранит словарь JSON в файле с атомарной заменой."""

import json
from pathlib import Path
from typing import Any


class JsonFileStore:
    """Дисковое JSON-хранилище; сбой чтения означает пустой кэш."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        return raw if isinstance(raw, dict) else {}

    def write(self, value: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            temporary.replace(self.path)
        except OSError:
            pass
