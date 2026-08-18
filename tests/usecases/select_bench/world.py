"""Общий инвентарь зеркал стенда: раздача, план, подделки службы раздач и паспорта."""

from __future__ import annotations

from collections.abc import Callable
from types import TracebackType

from torrcast.domain.media import Media
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.swarm_error import SwarmError
from torrcast.domain.torr_file import TorrFile
from torrcast.ports.json_value import JsonValue
from torrcast.usecases.select._plan import _Plan

GB = 1024**3
RUNTIME = 3600.0


def rel(
    name: str = "Кино / Movie (1999) BDRip 1080p",
    *,
    codec: str | None = "H.264",
    quality: str | None = "1080p",
    size_gb: float = 8.0,
    seeders: int = 100,
    voices: tuple[str, ...] = ("Дубляж",),
) -> Release:
    """Раздача со СВОИМ магнитом: без него прогревы неразличимы, а греются они разом."""
    return Release(
        raw_name=name,
        title="Кино",
        year=1999,
        quality=quality,
        codec=codec,
        voices=voices,
        size=int(size_gb * GB),
        seeders=seeders,
        magnet=f"magnet-{name}",
    )


def plan(
    ranked: list[Release],
    recode_at: float = 10.0,
    *,
    warn_mbit: float = 20.0,
    hard_mbit: float = 0.0,
    kin: list[Picture] | None = None,
) -> _Plan:
    """План картины: пул в порядке ранжира и включённое перекодирование, как в бою.

    ``recode_at`` не украшение: в бою перекодирование включено, и именно от него зависит,
    отказ ли HEVC или сплошной перекод. Ноль - перекодирование выключено.
    """
    return _Plan(
        picture=Picture(title="Кино", year=1999, releases=ranked),
        ranked=ranked,
        runtime=RUNTIME,
        warn_mbit=warn_mbit,
        recode_at=recode_at,
        hard_mbit=hard_mbit,
        kin=kin or [],
    )


class Torrents:
    """Служба раздач ровно в том объёме, в каком её дёргает подготовка релиза."""

    def __init__(self, files: list[TorrFile] | None = None, dead: set[str] | None = None) -> None:
        self.dropped: list[str] = []
        self.known = files if files is not None else [TorrFile(0, "movie.mkv", 4 * GB)]
        self.dead = dead or set()

    def add(self, magnet: str) -> str:
        return f"hash-{magnet}"

    def cache(self, torrent_hash: str) -> dict[str, JsonValue]:
        return {}

    def files(self, torrent_hash: str) -> list[TorrFile]:
        return self.known

    def wait_files(
        self, torrent_hash: str, timeout: float = 60.0, grace: float = 0.0
    ) -> list[TorrFile]:
        if torrent_hash in self.dead:  # раздача с мёртвым роем: пиров нет и не будет
            raise SwarmError(f"раздача не отдала метаданные за {timeout:.0f} с - нет пиров")
        return self.known

    def stream_url(self, torrent_hash: str, index: int) -> str:
        return f"http://ts/{torrent_hash}/{index}"

    def drop(self, torrent_hash: str) -> bool:
        self.dropped.append(torrent_hash)
        return True


def probes(releases: list[Release], *media: Media) -> Callable[..., Media]:
    """Подсунуть паспорт по раздаче, а не по порядку вызовов: греются они параллельно."""

    def read(
        source_url: str, /, timeout: float = 90.0, alive: Callable[[], bool] | None = None
    ) -> Media:
        for number, release in enumerate(releases):
            if f"hash-{release.magnet}/" in source_url and number < len(media):
                return media[number]
        return Media(RUNTIME, (), "h264")

    return read


class Said:
    """Индикатор, который ничего не рисует, а помнит фазы."""

    def __init__(self) -> None:
        self.phases: list[str] = []

    def phase(self, text: str) -> None:
        self.phases.append(text)

    def note(self, text: str) -> None:
        return None

    def stop(self) -> None:
        return None

    def __enter__(self) -> Said:
        return self

    def __exit__(
        self,
        kind: type[BaseException] | None,
        error: BaseException | None,
        trace: TracebackType | None,
    ) -> None:
        return None
