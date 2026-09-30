"""Что греет рука прогрева записей (:mod:`web.record_warm`)."""

from __future__ import annotations

from dataclasses import dataclass

from torrcast.domain.entry import Entry
from torrcast.ports.torrent_engine import TorrentEngine


@dataclass(frozen=True)
class WarmJob:
    """Что греть: раздача записи, адрес файла, закладка и имя файла (контейнер)."""

    magnet: str
    source: str
    at: float
    name: str

    @property
    def mark(self) -> tuple[str, str, int]:
        """Прогретое узнаётся по файлу и секунде закладки: сдвинулась - греть снова."""
        return self.magnet, self.source, round(self.at)

    @classmethod
    def of(cls, engine: TorrentEngine, entry: Entry, torrent_hash: str) -> WarmJob | None:
        """Файл записи в поднятой раздаче; без метаданных или без имени файла - ``None``.

        Имя несёт контейнер, а по нему цепочка решает, греть ли индекс mkv и какой кусок
        головы: пустое имя грело бы наугад раздачу, о которой служба ещё ничего не знает.
        """
        files = engine.files(torrent_hash)
        name = next((f.name for f in files if f.index == entry.file_idx), "")
        if not name:
            return None
        return cls(entry.magnet, engine.stream_url(torrent_hash, entry.file_idx), entry.pos, name)
