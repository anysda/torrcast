"""The first round of a search: the viewer's text, and beside it the recognized picture's names.

Radarr and Lampa with JacRed know the picture before they ask for its releases: a typo, a
short name or a poor round of the viewer's text then costs nothing, because the indexers
are asked «name year» and «original year» at once. The viewer's text is still asked: its
rows keep the namesakes and the rest of the franchise on the screen as before.

Prowlarr paces the requests to one host two seconds apart, in the order they arrive, so of
two texts sent at once one waits. The viewer's text leaves first: its rows are the only ones
making tiles and the ones the open card counts early (:func:`web.early_picture.early_picture`).
The names leave on its event, not after a pause: a slow list of indexers outlasts any pause.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from typing import Final

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.infra_error import InfraError
from torrcast.domain.joint_query import JOINT
from torrcast.domain.own_release import own_release
from torrcast.domain.picture import Picture
from torrcast.domain.raw_result import RawResult
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover._ask import _ask, _notify
from torrcast.usecases.discover.told_indexer import ToldIndexer

#: How long the round may wait for an offline map still being built on a cold start.
RECOGNIZE_WAIT: Final = 4.0
#: How long the names wait for the viewer's text to leave; a text that never leaves frees them.
HEAD: Final = 1.0


class NamedRound:
    """The circle's own client and the clients of the picture's names, as the preview sees them."""

    def __init__(self, source: IndexerClient) -> None:
        self.source = source
        self.known: MapPicture | None = None
        #: Set once the viewer's text has answered: its rows alone make the tiles, so the
        #: list can be judged while the names are still in flight.
        self.typed = threading.Event()
        #: The names were still asked when the viewer's text answered: judging its tiles
        #: then runs beside them. Answered last, the text leaves nothing to overlap.
        self.ahead = False
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

    def whole(self) -> bool:
        """Every client of the picture's names heard all of its indexers."""
        return all(_whole(client) for client in list(self._named))

    def gone(self) -> tuple[tuple[str, ...], tuple[str, ...]]:
        """Who dropped out of the rounds of the picture's names (:func:`_gone`)."""
        return _gone(list(self._named))

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
            asked = self._names(pool, spawn, on_indexer, name, query)
            try:
                raw = typed.result()
            finally:
                self.ahead = any(not future.done() for future in asked)
                self.typed.set()
            if not raw and not asked:
                # A map still being built on a cold start names the picture a moment later,
                # and a text nobody answered leaves time to ask by its names.
                asked = self._names(pool, spawn, on_indexer, name, query)
            told = [future.result() for future in asked]
        client.told.extend(said for one in told for said in one.told)
        return raw, [row for one in told for said in one.told for row in said[4]]

    def leads(self, found: list[Picture]) -> bool:
        """The first found picture is the recognized one, holding its own releases."""
        known = self.known
        return known is not None and bool(found) and own_release(found[0].releases[0], known)

    def _names(
        self,
        pool: ThreadPoolExecutor,
        spawn: Callable[[], IndexerClient],
        on_indexer: Callable[[IndexerClient], None] | None,
        name: str,
        query: str,
    ) -> list[Future[ToldIndexer]]:
        """Ask the indexers by the names of the picture the map knows ``query`` to be."""
        self.known = _search_state._search_recognize(query, RECOGNIZE_WAIT) if query else None
        texts = _texts(self.known, name)
        # One client carries all the names to the indexer that takes them joined; the
        # others leave it alone (:mod:`~torrcast.domain.joint_query`).
        joints = [JOINT.join(texts) if not each else "" for each in range(len(texts))]
        asked = [pool.submit(self._one, spawn(), *pair) for pair in zip(texts, joints, strict=True)]
        if asked:
            _notify(on_indexer, self)
        return asked

    def _one(self, source: IndexerClient, text: str, joint: str) -> ToldIndexer:
        self._named.append(source)
        if (beside := getattr(source, "beside", None)) is not None:
            beside(joint)
        told = ToldIndexer(source)
        _behind(self.source)
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


def _behind(client: IndexerClient) -> None:
    """Let the viewer's text draw its slots at the hosts before the picture's names do."""
    sent = getattr(client, "sent", None)
    if callable(sent):
        sent(HEAD)


def _whole(client: IndexerClient) -> bool:
    whole = getattr(client, "whole", None)
    return bool(whole()) if callable(whole) else False


def _gone(clients: list[IndexerClient]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Names that did not answer and names Prowlarr took away, over clients that can tell."""
    silent: set[str] = set()
    banned: set[str] = set()
    for client in clients:
        if callable(gone := getattr(client, "gone", None)):
            quiet, taken = gone()
            silent.update(quiet)
            banned.update(taken)
    return tuple(sorted(silent - banned)), tuple(sorted(banned))


def _inflight(client: IndexerClient) -> list[RawResult]:
    peek = getattr(client, "inflight", None)
    return list(peek()) if peek is not None else []


__all__ = ["HEAD", "RECOGNIZE_WAIT", "NamedRound"]
