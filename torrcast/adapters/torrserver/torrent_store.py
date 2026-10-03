"""Описания раздач (.torrent) на диске рядом с состоянием показа, по infohash.

Ссылка Prowlarr живёт только в памяти процесса, который искал, а закладку после
перезапуска и процесс показа описание должно догнать без пиров: этим оно и держится
на диске. Файлов не больше :data:`CAP`, лишние уходят по давности последнего обращения.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Final

from torrcast.adapters.filesystem.state.state_path import state_path

#: Сколько описаний держать: одно - десятки килобайт, полка закладок много меньше.
CAP: Final = 200
_HEX: Final = re.compile(r"[0-9a-f]{40}")


class TorrentStore:
    """Каталог ``torrents`` рядом с файлом состояния: у каждого экземпляра свой."""

    def folder(self) -> Path:
        return state_path().with_name("torrents")

    def has(self, torrent_hash: str) -> bool:
        """Лежит ли описание раздачи на диске."""
        path = self._path(torrent_hash)
        return path is not None and path.is_file()

    def stored(self, torrent_hash: str) -> bytes | None:
        """Байты описания или ``None``; прочитанное помечается как свежее."""
        path = self._path(torrent_hash)
        if path is None:
            return None
        try:
            data = path.read_bytes()
            os.utime(path)
        except OSError:
            return None
        return data

    def store(self, torrent_hash: str, data: bytes) -> None:
        """Положить описание атомарно (tmp + rename) и подрезать каталог до :data:`CAP`."""
        path = self._path(torrent_hash)
        if path is None:
            return
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            tmp = path.with_name(f".{path.name}.{os.getpid()}")
            tmp.write_bytes(data)
            os.replace(tmp, path)
            files = sorted(path.parent.glob("*.torrent"), key=lambda p: p.stat().st_mtime)
            for old in files[: max(0, len(files) - CAP)]:
                old.unlink(missing_ok=True)
        except OSError:
            return

    def _path(self, torrent_hash: str) -> Path | None:
        """Путь описания; хэш не из 40 hex - пути нет, а не обход каталога."""
        key = torrent_hash.casefold()
        return self.folder() / f"{key}.torrent" if _HEX.fullmatch(key) else None


#: Хранилище процесса: пишет описатель, читают он же и закладка после перезапуска.
STORE: Final = TorrentStore()

__all__ = ["CAP", "STORE", "TorrentStore"]
