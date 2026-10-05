"""A tracker's twin for the picture's names: the same catalog under a second host name.

Prowlarr spaces requests to one host two seconds apart (``HttpIndexerBase.RateLimit``), and
a search asks RuTor twice: the viewer's text and the picture's name. The text stood behind
the last search's name or the shelves' feed: "Тачки" answered at 5.45 s, its text left
RuTor's queue at +2.0 (stand .123, 05.10). Prowlarr keys that queue by the host, so RuTor
at a second name is a second queue: two requests sent at once answered in 0.6-0.9 s each,
one name took 0.7 and 2.7-3.1 s (stand .123, 05.10). The shelves' feed goes there too:
the viewer's text stood behind it.
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.twin_base import TWIN, twin_base


def names_twin(pairs: Sequence[Indexer], names: bool) -> list[Indexer]:
    """Whom a request asks: the viewer's text never asks a twin, the rest ask it instead.

    The rest are the picture's names and the shelves' feed: background to the viewer's text.
    A tracker whose twin is not among ``pairs`` (not installed, down or banned) keeps them.
    """
    if not names:
        return [pair for pair in pairs if not pair[1].endswith(TWIN)]
    twins = {twin_base(name) for _num, name in pairs if name.endswith(TWIN)}
    return [pair for pair in pairs if pair[1] not in twins]


__all__ = ["names_twin"]
