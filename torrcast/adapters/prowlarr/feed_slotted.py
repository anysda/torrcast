"""The shelves' feed apart (:mod:`.feed_apart`), each request drawing its slot at its host.

The feed is a request of ours in Prowlarr's host queues like any other, but it went past
:class:`~torrcast.adapters.prowlarr.host_slots.HostSlots`: the viewer's text did not know
RuTor held it and lost its rows past the budget ("Тачки", +3.28 s, stand, 05.10). Drawn,
the text counts its budget past the feed's slot.

RuTor's feed asks RuTor itself, not its twin: the twin's queue is the picture's names', and
the feed there put the second name of the search after a restart four seconds in ("Тачки"
4.72-5.47 s, stand, 05.10). A name never stands in RuTor's queue
(:func:`~torrcast.domain.names_twin.names_twin`), so the viewer's text never waits behind
one; behind the feed it waits a slot at most, once per shelves pass after a quiet spell.
"""

from __future__ import annotations

import threading
from collections.abc import Sequence
from typing import Any

from torrcast.adapters.prowlarr.feed_apart import feed_apart
from torrcast.adapters.prowlarr.feed_url import feed_url
from torrcast.adapters.prowlarr.host_slots import HostSlots
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.domain.circle_indexers import Indexer
from torrcast.domain.feed_rows import FeedRows
from torrcast.domain.names_twin import names_twin


def feed_slotted(
    api: ProwlarrApi, slots: HostSlots, usable: Sequence[Indexer], limit: int, within: float
) -> FeedRows:
    """The feed of ``usable`` (a tracker's twin left to the names), ``within`` seconds.

    Each request draws its indexer's slot as it leaves and stays in flight till it ends.
    """
    api.open()  # сессия поднимается ДО потоков: ленивая сборка внутри них - гонка
    pairs = names_twin(usable, names=False)
    urls = [feed_url(api.base_url, api.apikey, limit, number) for number, _name in pairs]
    names = dict(zip(urls, (name for _num, name in pairs), strict=True))

    def get(url: str) -> Any:
        done = threading.Event()
        if (slot := slots.claim(names[url], within)) is not None:
            slots.leave(names[url], slot.ticket)  # it goes at once: nothing goes ahead of it
        slots.sent(names[url], done)
        try:
            return api.get_json(url)
        finally:
            done.set()

    return feed_apart(get, urls, within)


__all__ = ["feed_slotted"]
