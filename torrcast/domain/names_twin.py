"""A tracker's twin for the picture's names: the same catalog under a second host name.

Prowlarr spaces requests to one host two seconds apart (``HttpIndexerBase.RateLimit``), and
a search asks RuTor twice: the viewer's text and the picture's name. The text stood behind
the last search's name or the shelves' feed: "Тачки" answered at 5.45 s, its text left
RuTor's queue at +2.0 (stand, 05.10). Prowlarr keys that queue by the host, so RuTor
at a second name is a second queue: two requests sent at once answered in 0.6-0.9 s each,
one name took 0.7 and 2.7-3.1 s (stand, 05.10).

A name never asks the tracker itself while its twin is there, even with the twin's queue
longer: the next search's text, a second later, stood behind such a name 3.0 s instead of
1.0 behind its own last text (merge check, 05.10). The viewer's text does not wait for a name.
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.twin_base import TWIN, twin_base


def names_twin(pairs: Sequence[Indexer], names: bool) -> list[Indexer]:
    """Whom a request asks: the picture's ``names`` ask a twin for its tracker, the rest never.

    A tracker whose twin is not among ``pairs`` (not installed, down or banned) keeps its names.
    """
    if not names:
        return [pair for pair in pairs if not pair[1].endswith(TWIN)]
    twins = {twin_base(name) for _num, name in pairs if name.endswith(TWIN)}
    return [pair for pair in pairs if pair[1] not in twins]


__all__ = ["names_twin"]
