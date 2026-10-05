"""A twin is switched by its tracker: RuTor turned off by hand is not asked at its second host."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.twin_base import TWIN, twin_base


def twin_follows(enabled: Sequence[Indexer]) -> list[Indexer]:
    """The ``enabled`` indexers without a twin whose tracker is not among them."""
    trackers = {name for _num, name in enabled if not name.endswith(TWIN)}
    return [
        pair for pair in enabled if not pair[1].endswith(TWIN) or twin_base(pair[1]) in trackers
    ]


__all__ = ["twin_follows"]
