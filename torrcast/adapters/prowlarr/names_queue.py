"""Which of two queues to a tracker the picture's name stands in: the tracker's or its twin's.

The twin (:mod:`~torrcast.domain.names_twin`) frees the viewer's text from the names, but the
shelves' feed goes there too, and it is the rebuild's first request after a restart. When it
left with the first search, both names stood behind it at the twin while RuTor itself sat
idle after the text: "Тачки" 4.72-5.47 s, the feed at -0.05, the names at +1.81 and +3.78,
RuTor's text alone at +0.34 (stand, 05.10, five blocks). A name goes where its slot starts
first; on a tie, to the twin, which the next search's text does not need.
"""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.twin_base import TWIN, twin_base


def names_queue(slots: HostSlots, pairs: Sequence[Indexer]) -> list[Indexer]:
    """Whom a circle of the picture's names asks: one of a tracker and its twin, sooner first.

    A tracker without its twin among ``pairs`` is asked itself, a twin without its tracker too.
    """
    twins = {twin_base(name): (num, name) for num, name in pairs if name.endswith(TWIN)}
    trackers = {name for _num, name in pairs if not name.endswith(TWIN)}
    picked: list[Indexer] = []
    for num, name in pairs:
        if name.endswith(TWIN):
            if twin_base(name) not in trackers:
                picked.append((num, name))
            continue
        twin = twins.get(name)
        if twin is not None and slots.starts(twin[1]) <= slots.starts(name):
            picked.append(twin)
        else:
            picked.append((num, name))
    return picked


__all__ = ["names_queue"]
