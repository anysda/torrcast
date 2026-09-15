"""The first round of a search: the viewer's text, and beside it the recognized picture's names.

Radarr and Lampa with JacRed know the picture before they ask for its releases: a typo, a
short name or a poor round of the viewer's text then costs nothing, because the indexers
are asked «name year» and «original year» at once. The viewer's text is still asked: its
rows keep the namesakes and the rest of the franchise on the screen as before.
"""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from contextlib import suppress
from typing import Final

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.infra_error import InfraError
from torrcast.domain.own_release import own_release
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._ask import _ask, _notify
from torrcast.usecases.discover.told_indexer import ToldIndexer

#: How long the round may wait for an offline map still being built on a cold start.
RECOGNIZE_WAIT: Final = 4.0


class NamedRound:
    """The circle's own client and the clients of the picture's names, as the preview sees them."""

    def __init__(self, source: IndexerClient) -> None:
        self.source = source
        self.known: MapPicture | None = None
        self._named: list[IndexerClient] = []

    @property
    def cap_floor(self) -> float:
        return self.source.cap_floor

    @cap_floor.setter
    def cap_floor(self, value: float) -> None:
        self.source.cap_floor = value

    @property
    def over_goal(self) -> bool:
        return self.source.over_goal

    @over_goal.setter
    def over_goal(self, value: bool) -> None:
        self.source.over_goal = value

    def search(self, query: str) -> list[RawResult]:
        return self.source.search(query)

    def late(self) -> list[RawResult]:
        return self.source.late()

    def spare(self) -> float:
        return self.source.spare()

    def inflight(self) -> list[RawResult]:
        """Rows of the viewer's text that already answered."""
        return _inflight(self.source)

    def named_inflight(self) -> list[RawResult]:
        """Rows of the picture's names that already answered."""
        return [row for client in list(self._named) for row in _inflight(client)]

    def ask(
        self,
        client: ToldIndexer,
        spawn: Callable[[], IndexerClient],
        on_indexer: Callable[[IndexerClient], None] | None,
        name: str,
        query: str,
    ) -> tuple[list[RawResult], list[RawResult]]:
        """Rows of ``name`` and rows of the names of the picture ``query`` is, asked at once.

        An empty ``query`` recognizes nothing: the round is then the plain search of ``name``.
        """
        with ThreadPoolExecutor(max_workers=3, thread_name_prefix="named-round") as pool:
            typed = pool.submit(_ask, client, name)
            self.known = _search_state._search_recognize(query, RECOGNIZE_WAIT) if query else None
            asked = [pool.submit(self._one, spawn(), text) for text in _texts(self.known, name)]
            if asked:
                _notify(on_indexer, self)
            raw = typed.result()
            told = [future.result() for future in asked]
        client.told.extend(said for one in told for said in one.told)
        return raw, [row for one in told for said in one.told for row in said[4]]

    def leads(self, found: list[Picture]) -> bool:
        """The first found picture is the recognized one, holding its own releases."""
        known = self.known
        return known is not None and bool(found) and own_release(found[0].releases[0], known)

    def _one(self, source: IndexerClient, text: str) -> ToldIndexer:
        self._named.append(source)
        told = ToldIndexer(source)
        # The viewer's text answers for the catalogue's health; a name only adds rows.
        with suppress(InfraError):
            _ask(told, text)
        return told


def _texts(known: MapPicture | None, name: str) -> list[str]:
    """«name year» and «original year»; a series is asked without its first year."""
    if known is None:
        return []
    tail = "" if known.series or known.year is None else f" {known.year}"
    names = (each for each in (known.name, known.original) if each)
    texts = {f"{each}{tail}".casefold(): f"{each}{tail}" for each in names}
    texts.pop(name.casefold(), None)
    return list(texts.values())


def _inflight(client: IndexerClient) -> list[RawResult]:
    peek = getattr(client, "inflight", None)
    return list(peek()) if peek is not None else []


__all__ = ["RECOGNIZE_WAIT", "NamedRound"]
