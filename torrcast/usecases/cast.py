"""Запускает выбранный торрент на переданном приёмнике."""

from dataclasses import dataclass

from torrcast.ports.receiver import Receiver
from torrcast.ports.torrent_engine import TorrentEngine


@dataclass(slots=True)
class Cast:
    """Получает адрес файла у движка и передаёт его приёмнику."""

    torrents: TorrentEngine
    receiver: Receiver

    def run(self, magnet: str, file_index: int, title: str = "", start_at: float = 0.0) -> str:
        torrent_hash = self.torrents.add(magnet)
        url = self.torrents.stream_url(torrent_hash, file_index)
        self.receiver.play(url, title, start_at)
        return torrent_hash
