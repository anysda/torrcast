"""Идущие круги поиска по строке: что уже ответило и весь ли каталог ответил.

Круг поиска один на строку, но спрашивают о нём и те, кто его не заводил: карточка
плитки ждёт круг, который завёл прогрев, и до его конца видела только скелет. Здесь
клиенты индексеров идущего круга лежат под его строкой, пока круг не кончится, и превью
читает их выдачу прямо сейчас (:meth:`CircleWatch.rows`), ничего не спрашивая в сеть.

Кроме ответивших, круг кладёт сюда пул, который уже взял (:meth:`CircleWatch.keep`): строки,
привезённые доливом опоздавших и доборами, входят в счёт превью, как только круг их принял.

Второе, что отсюда видно, - полнота круга (:func:`_heard_all`): «раздач нет» правдиво
только тогда, когда ответил каждый спрошенный индексер, а не когда кто-то смолчал.
"""

from __future__ import annotations

import threading
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

import torrcast.usecases.discover._search_state as _search_state
from torrcast.domain.not_found_error import NotFoundError
from torrcast.ports.journal.slot import journal
from torrcast.usecases.discover.named_round import NamedRound, _gone, _whole
from torrcast.usecases.discover.told_circle import ToldCircle

if TYPE_CHECKING:
    from torrcast.domain.facts.map_picture import MapPicture
    from torrcast.domain.raw_result import RawResult
    from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
    from torrcast.usecases.select.plan import Plan

#: Что круг уже держит в руках: строки текста зрителя, строки имён картины и её карта.
Rows = tuple["list[RawResult]", "list[RawResult]", "MapPicture | None"]


def _heard_all(clients: list[IndexerClient]) -> bool:
    """Ответил ли каталог целиком: каждый клиент круга сам говорит, все ли ему ответили.

    Клиент, который этого сказать не умеет (круг с диска, подделка), полноты не доказал.
    """
    return bool(clients) and all(_whole(client) for client in clients)


class _Heard(list["IndexerClient"]):
    """Клиенты одного круга и пул, который круг уже взял в итог."""

    kept: list[RawResult]

    def __init__(self) -> None:
        super().__init__()
        self.kept = []


#: Круг, идущий в этом потоке: сюда :meth:`CircleWatch.keep` кладёт взятый пул.
_current: ContextVar[_Heard | None] = ContextVar("circle", default=None)


@dataclass
class CircleWatch:
    """Клиенты идущих кругов под их строкой; кончился круг - его здесь нет."""

    _running: dict[str, list[_Heard]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @contextmanager
    def watching(self, query: str) -> Iterator[_Heard]:
        """Список, в который круг кладёт своих клиентов, пока он идёт."""
        key = query.strip()
        heard = _Heard()
        with self._lock:
            self._running.setdefault(key, []).append(heard)
        try:
            yield heard
        finally:
            with self._lock:
                # По себе, а не по равенству: два пустых списка равны, а круги разные.
                circles = [each for each in self._running.get(key, []) if each is not heard]
                if circles:
                    self._running[key] = circles
                else:
                    self._running.pop(key, None)

    def run(
        self,
        query: str,
        on_indexer: Callable[[IndexerClient], None] | None,
        circle: Callable[[Callable[[IndexerClient], None]], list[Plan]],
    ) -> list[Plan]:
        """Круг под наблюдением; и планы, и отказ «ничего» несут метку полноты ``whole``."""
        with self.watching(query) as heard:
            token = _current.set(heard)

            def hear(client: IndexerClient) -> None:
                heard.append(client)
                if on_indexer is not None:
                    on_indexer(client)

            try:
                plans = circle(hear)
            except NotFoundError as nothing:
                nothing.whole = _heard_all(heard)
                nothing.silent, nothing.banned = _gone(heard)
                # The one line that tells a cut empty circle from a whole one on a stand.
                journal().emit(
                    "search",
                    "empty",
                    query=query,
                    whole=nothing.whole,
                    silent=list(nothing.silent),
                    banned=list(nothing.banned),
                )
                raise
            finally:
                _current.reset(token)
            if isinstance(plans, ToldCircle):
                plans.whole = _heard_all(heard)
            return plans

    @staticmethod
    def keep(raw: list[RawResult]) -> None:
        """Пул, который идущий в этом потоке круг уже взял: его строки входят в счёт превью."""
        heard = _current.get()
        if heard is not None:
            heard.kept = list(raw)

    def rows(self, query: str) -> Rows:
        """Выдача идущего круга по строке прямо сейчас; кругов несколько - самый богатый."""
        with self._lock:
            circles = [(list(heard), heard.kept) for heard in self._running.get(query.strip(), [])]
        best: Rows = ([], [], None)
        for clients, kept in circles:
            got = _peek(clients, kept)
            if len(got[0]) + len(got[1]) > len(best[0]) + len(best[1]):
                best = got
        return best


def _peek(clients: list[IndexerClient], kept: Sequence[RawResult] = ()) -> Rows:
    """Строки одного круга: взятый пул, у круга имён свой счёт, у остальных - что ответило."""
    raw: list[RawResult] = list(kept)
    named: list[RawResult] = []
    known = None
    for client in clients:
        if isinstance(client, NamedRound):
            named += client.named_inflight()
            known = client.known
            continue
        peek = getattr(client, "inflight", None)
        raw += peek() if peek is not None else []
    # Индексеры отдают одну раздачу каждый своей строкой, а круг клеит их в одну: без склейки
    # счёт до конца круга выходил больше итога и под конец падал (98 раздач, потом 84).
    merge = _search_state._search_catalogue.merge
    return merge(raw), merge(named), known


#: Один на процесс: круги заводят все, а читают их карточка и показ.
WATCH = CircleWatch()

__all__ = ["WATCH", "CircleWatch", "Rows"]
