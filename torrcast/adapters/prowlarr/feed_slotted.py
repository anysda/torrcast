"""The shelves' feed apart (:mod:`.feed_apart`), each request drawing its slot at its host.

The feed is a request of ours in Prowlarr's host queues like any other, but it went past
:class:`~torrcast.adapters.prowlarr.host_slots.HostSlots`: the picture of the queues did not
know the twin held it, and the names asked there as at an idle host. After a restart the
rebuild's feed left with the first search: "Тачки" 4.72-5.47 s, the names two slots behind
it at the twin (stand, 05.10). Drawn, it sends the names where the queue is shorter
(:mod:`.names_queue`).
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
    """The feed of ``usable`` (a tracker with a twin through the twin), ``within`` seconds.

    Each request draws its indexer's slot as it leaves and stays in flight till it ends.
    """
    api.open()  # сессия поднимается ДО потоков: ленивая сборка внутри них - гонка
    pairs = names_twin(usable, names=True)
    urls = [feed_url(api.base_url, api.apikey, limit, number) for number, _name in pairs]
    names = dict(zip(urls, (name for _num, name in pairs), strict=True))

    def get(url: str) -> Any:
        done = threading.Event()
        slots.claim(names[url], within)
        slots.sent(names[url], done)
        try:
            return api.get_json(url)
        finally:
            done.set()

    return feed_apart(get, urls, within)


__all__ = ["feed_slotted"]
