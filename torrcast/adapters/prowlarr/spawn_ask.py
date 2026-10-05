"""Один спрошенный индексер: свой поток, место под ответ и флаг «поток закончил».

Зовёт его круг по индексерам (:class:`torrcast.adapters.prowlarr.indexer_circle.IndexerCircle`)."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from torrcast.adapters.prowlarr.ask_indexer import ask_indexer
from torrcast.adapters.prowlarr.down_book import DOWN_BOOK
from torrcast.adapters.prowlarr.host_slots import PACE
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.search_url import search_url
from torrcast.domain.cut_short import cut_short
from torrcast.domain.infra_error import InfraError
from torrcast.domain.is_down import IN_TIME
from torrcast.domain.raw_result import RawResult
from torrcast.domain.response_budget import response_budget


@dataclass(slots=True)
class _Ask:
    """Один спрошенный индексер: место под ответ и флаг «поток закончил».

    Поток свой и демонский, а не из пула: опоздавший живёт дольше круга (TC-118), и
    пул задержал бы на нём выход процесса - потоки пула дожидаются на atexit, демонские
    умирают вместе с командой.
    """

    name: str
    budget: float
    done: threading.Event = field(default_factory=threading.Event)
    rows: list[RawResult] | None = None
    ms: int = 0
    err: InfraError | None = None
    #: Taken by whoever tells the book how this ask went: the circle that stopped waiting
    #: for it, or the thread when it ends. One ask is one outcome, never two.
    judge: threading.Lock = field(default_factory=threading.Lock)
    #: The circle stopped waiting for it inside its budget: the others had brought rows.
    waived: bool = False
    #: Its host slot's start (:meth:`~torrcast.adapters.prowlarr.host_slots.HostSlots.claim`).
    slot: float = 0.0
    #: Set by :func:`_drop` while the request still waits for its slot: it is never sent.
    stop: bool = False
    left: bool = False  # the request has gone to Prowlarr: there is no taking it back
    followers: int = 0  # other circles waiting on this very request (:func:`_follow`)


#: Requests on their way, by URL: one text goes to one indexer once at a time. Two circles of
#: one search sent Knaben the same text 4 s apart, and the second stood behind the first there.
_FLYING: dict[str, _Ask] = {}
_FLYING_LOCK = threading.Lock()


def _drop(ask: _Ask) -> bool:
    """Keep a request still waiting for its host slot from going; whether it was kept back.

    A circle of names that ended before its name left stopped waiting for it, and nobody reads
    the rows it would bring: sent, it only took the host's slot. On the stand a search's names
    left Knaben's queue after the search had answered, and the next search's text and its
    second-language circle stood behind two of them (20:36:54 and 20:36:58, 04.10, the worst
    warm search at 11.5 s).

    A request another circle follows is still read, so it goes (TC-1404).
    """
    with _FLYING_LOCK:
        if ask.left or ask.followers or ask.done.is_set():
            return False
        ask.stop = True
        for url in [url for url, one in _FLYING.items() if one is ask]:
            del _FLYING[url]
    ask.done.set()
    return True


def _follow(api: ProwlarrApi, query: str, limit: int, num: int, budget: float) -> _Ask | None:
    """Wait the request already on its way instead of sending it again; None if there is none.

    The answer is the twin's, and so is its one verdict to the book (``judge``): one request
    is one outcome, whichever circle tells it. Found and counted under one lock, the twin is
    never kept back by its own circle after this (TC-1404): a follower of a dropped request
    heard ``rows=None`` and took the indexer for silent.
    """
    with _FLYING_LOCK:
        twin = _FLYING.get(search_url(api.base_url, api.apikey, query, limit, num))
        if twin is None:
            return None
        twin.followers += 1
    ask = _Ask(name=twin.name, budget=budget, judge=twin.judge, left=True)  # holds no slot

    def work() -> None:
        twin.done.wait()
        ask.rows = None if twin.rows is None else list(twin.rows)
        ask.ms, ask.err = twin.ms, twin.err
        ask.done.set()

    threading.Thread(target=work, daemon=True, name=f"idx-{twin.name}").start()
    return ask


def spawn_ask(
    api: ProwlarrApi,
    query: str,
    limit: int,
    num: int,
    name: str,
    budget: float,
    queued: float = 0.0,
) -> _Ask:
    """Пустить один индексер отдельным потоком и вернуть место под его ответ.

    ``queued`` - seconds the request stands in Prowlarr's queue to the host: the request's
    own life starts when it leaves the queue, not when it is sent. The circle's wait
    ``budget`` comes whole from the caller, who knows whether it waits the queue too.

    A queued request leaves half a pace before its slot, not at once: Prowlarr queues by
    arrival, and the names sent a few milliseconds after the viewer's text overtook it at
    every host (stand 01.10: "Призрак в доспехах" left Knaben's queue at +4.24, behind both
    names, and the show started at 12.7 s).
    """
    ask = _Ask(name=name, budget=budget)
    url = search_url(api.base_url, api.apikey, query, limit, num)
    book = DOWN_BOOK.where()
    with _FLYING_LOCK:
        _FLYING[url] = ask

    def work() -> None:
        # Бюджет ``ask`` отвечает только за критический путь. Сам запрос живёт в
        # личный срок индексера, чтобы потолок второго круга не обрывал быстрый
        # ответ на границе, а поздний ответ опорного мог доехать в долив.
        if (hold := max(0.0, queued - PACE / 2)) > 0:
            time.sleep(hold)
        with _FLYING_LOCK:
            ask.left = not ask.stop
        if not ask.left:
            return
        life = response_budget(name) + queued - hold
        ask.rows, ask.ms, ask.err = ask_indexer(api.get_json, url, life)
        with _FLYING_LOCK:
            if _FLYING.get(url) is ask:
                del _FLYING[url]
        ask.done.set()
        if ask.judge.acquire(blocking=False):
            in_time = ask.rows is not None and ask.ms <= IN_TIME * 1000
            # A zero no sooner than the adapter's cut is the source giving up, not an answer.
            gave_up = ask.rows == [] and bool(cut_short({name: 0}, {name: ask.ms}))
            DOWN_BOOK.hear(name, answered=in_time and not gave_up, where=book)

    threading.Thread(target=work, daemon=True, name=f"idx-{name}").start()
    return ask
