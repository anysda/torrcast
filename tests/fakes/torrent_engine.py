"""Изображает для тестов движок торрентов и записывает обращения."""

from dataclasses import dataclass, field
from typing import Any

from torrcast.domain.torr_file import TorrFile


@dataclass
class FakeTorrentEngine:
    torrent_hash: str = "hash"
    torrent_files: list[TorrFile] = field(default_factory=list)
    cached: dict[str, Any] = field(default_factory=dict)
    added: list[str] = field(default_factory=list)
    dropped: list[str] = field(default_factory=list)
    awaited: list[tuple[str, float, float]] = field(default_factory=list)
    stream_requests: list[tuple[str, int]] = field(default_factory=list)
    #: Служба молчит: снос не удался, счётчик кэша спросить не у кого.
    silent: bool = False

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return self.torrent_hash

    def cache(self, torrent_hash: str) -> dict[str, Any]:
        return dict(self.cached)

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        return not self.silent

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return list(self.torrent_files)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        self.stream_requests.append((torrent_hash, index))
        return f"http://fake/{torrent_hash}/{index}"

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        self.awaited.append((torrent_hash, timeout, float(grace)))
        return list(self.torrent_files)
