"""Изображает для тестов движок торрентов и записывает обращения."""

from dataclasses import dataclass, field

from torrcast.domain.torr_file import TorrFile


@dataclass
class FakeTorrentEngine:
    torrent_hash: str = "hash"
    torrent_files: list[TorrFile] = field(default_factory=list)
    added: list[str] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)
    stream_requests: list[tuple[str, int]] = field(default_factory=list)

    def add(self, magnet: str) -> str:
        self.added.append(magnet)
        return self.torrent_hash

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return list(self.torrent_files)

    def stream_url(self, torrent_hash: str, index: int) -> str:
        self.stream_requests.append((torrent_hash, index))
        return f"http://fake/{torrent_hash}/{index}"

    def remove(self, torrent_hash: str) -> bool:
        self.removed.append(torrent_hash)
        return True
