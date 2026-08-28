"""Завод захода упаковки: чем прогрев поднимает ffmpeg на свой кусок фильма."""

from collections.abc import Callable
from pathlib import Path
from typing import Protocol

from torrcast.domain.profile import CAUTIOUS
from torrcast.domain.segment_container import MPEGTS, SegmentContainer
from torrcast.ports.feed_grid import FeedGrid
from torrcast.ports.warm_environment.warm_pack import WarmPack


class WarmPacker(Protocol):
    """Завод захода упаковки в объёме, который зовёт прогрев.

    Подпись снята с настоящего вызова (:func:`torrcast.usecases.warm.run`), а не
    придумана: команда ffmpeg уже собрана, каталоги названы оба - куда класть наружу и
    где ffmpeg пишет своё, - а сетка, потолок веса куска и решатель тяжёлого куска
    приходят по имени.

    🔴 ``cap`` тут назван именно потому, что его однажды не назвали: договор повторял
    вызов, вызов потолка не передавал, и заход прогрева мерил куски осторожным
    умолчанием завода вместо потолка ТОГО приёмника, для которого греет. Умолчание
    остаётся осторожным - незнакомому приёмнику достаётся оно же.
    """

    def start(
        self,
        command: list[str],
        out: Path,
        run: Path,
        first: int = 0,
        *,
        last: int = -1,
        grid: FeedGrid | None = None,
        shrink: Callable[[int, int], bool | None] | None = None,
        cap: int = CAUTIOUS.max_segment_bytes,
        container: SegmentContainer = MPEGTS,
    ) -> WarmPack:
        """Поднять ffmpeg на куски с ``first`` по ``last`` и вернуть идущий заход."""
