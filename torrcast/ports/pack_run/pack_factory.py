"""Завод прогона упаковки: чем лента показа поднимает ffmpeg на своё место фильма."""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol, TypeAlias

from torrcast.domain.profile import CAUTIOUS
from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.pack_run.pack_run import PackRun

#: Кого позвать, когда сегмент ушёл наружу: ``(слот, чем он ушёл)``.
PackTold: TypeAlias = Callable[[int, str], None]
#: Кого спросить про кусок по его весу: ``(слот, вес копии) -> bool``.
PackAsked: TypeAlias = Callable[[int, int], bool]


class PackFactory(Protocol):
    """Завод прогона упаковки в объёме, в каком его зовёт лента показа.

    Подпись снята с настоящих вызовов (:mod:`torrcast.usecases.feed_pack.feed_restart`,
    :mod:`torrcast.usecases.feed_pack.feed_shrink`): команда ffmpeg уже собрана, каталоги
    названы оба - куда класть наружу и где ffmpeg пишет своё, - а соседи по показу
    приходят ручками, которые прогон зовёт со своей выкладки.
    """

    def start(
        self,
        command: list[str],
        out: Path,
        run: Path,
        first: int = 0,
        spare: Path | None = None,
        told: PackTold | None = None,
        hold: PackAsked | None = None,
        shrink: PackAsked | None = None,
        last: int = -1,
        at: float = 0.0,
        rate: float = 0.0,
        burst: float = 0.0,
        grid: FeedGrid | None = None,
        cap: int = CAUTIOUS.max_segment_bytes,
    ) -> PackRun:
        """Поднять ffmpeg командой ``command`` и вернуть идущий прогон."""
