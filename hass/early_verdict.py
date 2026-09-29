"""The poster verdict of the blocking search, started on the viewer's text alone (TC-1284).

The tiles come from the rows of the viewer's text, and the picture's names only add
releases to them: once the viewer's text has answered, the list is known seconds before the
circle ends. The verdict (:class:`hass.hit_posters.HitPosters`) then runs beside the
names instead of after them. The list's own verdict (:func:`hass.offer_within.offer_within`)
finds these pictures claimed or judged and waits for the rest only: before, the first
search after a start and the long lists paid the whole one-second limit on top of the circle.
"""

from __future__ import annotations

import threading
from collections.abc import Callable

from hass.peek_client import peek_client
from torrcast.domain.json_value import JsonValue
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.named_round import NamedRound


def early_verdict(
    query: str, offer: Callable[[list[JsonValue]], list[JsonValue]]
) -> Callable[[IndexerClient], None]:
    """The circle's ``on_indexer`` hook judging ``query``'s tiles once the viewer's text is in."""
    started = threading.Event()

    def hook(client: IndexerClient) -> None:
        if not isinstance(client, NamedRound) or started.is_set():
            return
        started.set()
        threading.Thread(
            target=_judge, args=(query, client, offer), daemon=True, name="early-verdict"
        ).start()

    return hook


def _judge(
    query: str, client: NamedRound, offer: Callable[[list[JsonValue]], list[JsonValue]]
) -> None:
    client.typed.wait()
    # Answered last, the viewer's text leaves no names to overlap: judging here would
    # only race the list's own build for the processor.
    records = peek_client(query, client) if client.ahead else []
    if not records:
        return
    # A refused verdict costs the list nothing: its own verdict asks again.
    try:
        offer(records)
    except (TorrcastError, OSError):
        return


__all__ = ["early_verdict"]
