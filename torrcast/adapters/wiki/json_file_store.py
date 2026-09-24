"""Хранит словарь JSON в файле с атомарной заменой."""

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any

#: Разобранный файл по пути и его отметке ``(mtime_ns, size)``. Кэш справки читают на
#: каждый заход карточки и каждую плитку; разбор 0.9 МБ стоил 15 мс под GIL (живой экземпляр).
_PARSED: dict[Path, tuple[tuple[int, int], dict[str, Any]]] = {}
_LOCK = threading.Lock()


class JsonFileStore:
    """Дисковое JSON-хранилище; сбой чтения означает пустой кэш."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def read(self) -> dict[str, Any]:
        try:
            stamp = _stamp(self.path)
            with _LOCK:
                known = _PARSED.get(self.path)
            if known is not None and known[0] == stamp:
                return dict(known[1])
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}
        if not isinstance(raw, dict):
            return {}
        with _LOCK:
            _PARSED[self.path] = stamp, raw
        return dict(raw)

    def write(self, value: dict[str, Any]) -> None:
        # Свой временный файл на запись: общий ``.tmp`` два писателя разом открывали бы
        # с усечением один и тот же.
        temporary: Path | None = None
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, name = tempfile.mkstemp(
                dir=self.path.parent, prefix=f".{self.path.name}.", suffix=".tmp"
            )
            temporary = Path(name)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                handle.write(json.dumps(value, ensure_ascii=False))
            temporary.replace(self.path)
            with _LOCK:
                _PARSED[self.path] = _stamp(self.path), dict(value)
        except OSError:
            if temporary is not None:
                temporary.unlink(missing_ok=True)


def _stamp(path: Path) -> tuple[int, int]:
    """Отметка файла, по которой разобранное можно отдать без чтения."""
    stat = path.stat()
    return stat.st_mtime_ns, stat.st_size
