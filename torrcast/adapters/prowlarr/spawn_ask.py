"""Один спрошенный индексер: свой поток, место под ответ и флаг «поток закончил».

Зовёт его круг по индексерам (:class:`torrcast.adapters.prowlarr.indexer_circle.IndexerCircle`)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from torrcast.adapters.prowlarr.ask_indexer import ask_indexer
from torrcast.adapters.prowlarr.down_book import DOWN_BOOK
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


#: Requests on their way, by URL: one text goes to one indexer once at a time. Two circles of
#: one search sent Knaben the same text 4 s apart, and the second stood behind the first there.
_FLYING: dict[str, _Ask] = {}
_FLYING_LOCK = threading.Lock()


def _in_flight(api: ProwlarrApi, query: str, limit: int, num: int) -> _Ask | None:
    """The ask already on its way with this very request, if there is one."""
    with _FLYING_LOCK:
        return _FLYING.get(search_url(api.base_url, api.apikey, query, limit, num))


def _follow(twin: _Ask, budget: float) -> _Ask:
    """Wait the request already on its way instead of sending it again.

    The answer is the twin's, and so is its one verdict to the book (``judge``): one request
    is one outcome, whichever circle tells it.
    """
    ask = _Ask(name=twin.name, budget=budget, judge=twin.judge)

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

    ``queued`` - seconds the request stands in Prowlarr's queue to the host: the budget and
    the request's own life start when it leaves the queue, not when it is sent.
    """
    ask = _Ask(name=name, budget=budget + queued)
    url = search_url(api.base_url, api.apikey, query, limit, num)
    book = DOWN_BOOK.where()
    with _FLYING_LOCK:
        _FLYING[url] = ask

    def work() -> None:
        # Бюджет ``ask`` отвечает только за критический путь. Сам запрос живёт в
        # личный срок индексера, чтобы потолок второго круга не обрывал быстрый
        # ответ на границе, а поздний ответ опорного мог доехать в долив.
        ask.rows, ask.ms, ask.err = ask_indexer(api.get_json, url, response_budget(name) + queued)
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
