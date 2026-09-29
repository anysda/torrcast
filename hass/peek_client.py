"""The records a search client already holds, before its circle is over (TC-1126).

Shared by the progressive preview (:mod:`hass.search_progress`) and the early poster
verdict of the blocking search (:mod:`hass.early_verdict`): both read what has answered
so far with the same rule as the full circle, without a single extra request.
"""

from __future__ import annotations

from hass.search_results import _hit
from torrcast.domain.json_value import JsonValue
from torrcast.domain.menu_order import menu_order
from torrcast.domain.raw_result import RawResult
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.named_round import NamedRound
from torrcast.usecases.discover.recognized_pick import recognized_pick


def peek_client(query: str, client: IndexerClient | None) -> list[JsonValue]:
    """Records of the pictures in the rows ``client`` holds right now."""
    peek = getattr(client, "inflight", None)
    raw: list[RawResult] = peek() if peek is not None else []
    named = client.named_inflight() if isinstance(client, NamedRound) else []
    if not raw and not named:
        return []
    known = client.known if isinstance(client, NamedRound) else None
    found = menu_order(recognized_pick(query, raw, named, known)[1])
    return [_hit(picture, number, default=False) for number, picture in enumerate(found, start=1)]


__all__ = ["peek_client"]
