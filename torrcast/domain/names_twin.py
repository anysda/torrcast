"""A tracker's twin for the picture's names: the same catalog under a second host name.

Prowlarr spaces requests to one host two seconds apart (``HttpIndexerBase.RateLimit``), and
a search asks RuTor twice: the viewer's text and the picture's name. The text stood behind
the last search's name or the shelves' feed: "Тачки" answered at 5.45 s, its text left
RuTor's queue at +2.0 (stand .123, 05.10). Prowlarr keys that queue by the host, so RuTor
at a second name is a second queue: two requests sent at once answered in 0.6-0.9 s each,
one name took 0.7 and 2.7-3.1 s (stand .123, 05.10).
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Final

from torrcast.domain.circle_indexers import Indexer

#: What a twin's name adds to its tracker's (the installer names it so).
TWIN: Final = " names"


def twin_base(name: str) -> str:
    """The tracker a twin stands for; any other name as it is."""
    return name.removesuffix(TWIN)


def by_circle(pairs: Sequence[Indexer], names: bool) -> list[Indexer]:
    """Whom a circle asks: the text never asks a twin, the names ask it instead of its tracker.

    A tracker whose twin is not among ``pairs`` (not installed, down or banned) keeps the names.
    """
    if not names:
        return [pair for pair in pairs if not pair[1].endswith(TWIN)]
    twins = {twin_base(name) for _num, name in pairs if name.endswith(TWIN)}
    return [pair for pair in pairs if pair[1] not in twins]


__all__ = ["TWIN", "by_circle", "twin_base"]
