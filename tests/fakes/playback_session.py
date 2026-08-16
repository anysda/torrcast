"""Изображает внешний сеанс для сценариев stop и status."""

from dataclasses import dataclass, field

from torrcast.domain.playback_snapshot import PlaybackSnapshot


@dataclass
class FakePlaybackSession:
    playing: bool = False
    play_key: str = ""
    shown: PlaybackSnapshot | None = None
    reserve: str = ""
    address: str = "http://127.0.0.1:8080"
    receiver: str = "chromecast"
    stopped: int = 0
    released: list[str] = field(default_factory=list)

    def active(self) -> bool:
        return self.playing

    def key(self) -> str:
        return self.play_key

    def stop(self) -> None:
        self.stopped += 1

    def snapshot(self, key: str = "") -> PlaybackSnapshot | None:
        return self.shown

    def release(self, torrent_hash: str) -> None:
        self.released.append(torrent_hash)

    def cache_reserve(self, snapshot: PlaybackSnapshot) -> str:
        return self.reserve

    def stream_address(self) -> str:
        return self.address

    def receiver_name(self) -> str:
        return self.receiver
