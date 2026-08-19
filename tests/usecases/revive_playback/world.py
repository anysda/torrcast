"""Поддельный мир оживления показа: приёмник по сценарию, живая упаковка, ручные часы.

Общий инвентарь зеркал пакета: сна тут нет вовсе, а решения показа видно списками.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from tests.conftest import fake_packer
from torrcast.adapters.stream_pack.grid import Grid
from torrcast.adapters.stream_pack.hls_dir import hls_dir
from torrcast.domain.position import Position
from torrcast.usecases.feed_pack.feed import Feed


@dataclass
class FakeReceiver:
    """Приёмник по сценарию: очередь состояний, как их отдаёт живой телевизор."""

    script: list[tuple[float, str]] = field(default_factory=list)
    #: Места, с которых у приёмника просили поднять показ (:meth:`replay`).
    replayed: list[float] = field(default_factory=list)
    #: Чем приёмник отвечает на подъём: место или отказ отрицательным числом.
    answer: float = 0.0

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)

    def replay(self, pos: float) -> float:
        self.replayed.append(pos)
        return self.answer


@dataclass
class PlainReceiver:
    """Приёмник, который поднимать показ не умеет: у него нет :meth:`replay`."""

    script: list[tuple[float, str]] = field(default_factory=list)

    def play(self, url: str, title: str = "", at: float = 0.0) -> None:
        return None

    def stop(self, quit_app: bool = False) -> None:
        return None

    def position(self, front: float = 0.0) -> Position:
        pos, state = self.script.pop(0) if self.script else (0.0, "IDLE")
        return Position(pos, 7200.0, state in {"PLAYING", "BUFFERING"}, state)


@dataclass
class FakeSupply:
    """Источник показа: отвечает ли служба и вернулась ли раздача с трекерами."""

    silence: str = ""
    restored: bool = False
    torrent_hash: str = "hash"
    magnet: str = "magnet:?xt=hash"
    lost: str = ""
    #: Сколько раз источник спрашивали: вопрос стоит запроса и задаётся не в горячем пути.
    asked: int = 0

    def check(self) -> str:
        self.asked += 1
        return self.silence


def feed_with_segments(tmp_path: Path, slots: int = 60) -> Feed:
    """Упаковка на готовые сегменты ровной сетки; ffmpeg за ней настоящий не стоит."""
    out = hls_dir(str(tmp_path / "hls"))
    for slot in range(slots):
        (out / f"v{slot}.ts").write_bytes(b"x")
    feed = Feed(source="", audio=0, out=out, grid=Grid.uniform(7200.0), keep=40.0, wait=0.0)
    feed.packer = fake_packer(out, first=0)
    return feed
