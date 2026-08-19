"""Один спрошенный индексер: свой поток, место под ответ и флаг «поток закончил».

Зовёт его круг по индексерам (:class:`torrcast.adapters.prowlarr.indexer_circle.IndexerCircle`)."""

from __future__ import annotations

import threading
from dataclasses import dataclass, field

from torrcast.adapters.prowlarr.ask_indexer import ask_indexer
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.search_url import search_url
from torrcast.domain.infra_error import InfraError
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


def spawn_ask(api: ProwlarrApi, query: str, limit: int, num: int, name: str, budget: float) -> _Ask:
    """Пустить один индексер отдельным потоком и вернуть место под его ответ."""
    ask = _Ask(name=name, budget=budget)
    url = search_url(api.base_url, api.apikey, query, limit, num)

    def work() -> None:
        # Бюджет ``ask`` отвечает только за критический путь. Сам запрос живёт в
        # личный срок индексера, чтобы потолок второго круга не обрывал быстрый
        # ответ на границе, а поздний ответ опорного мог доехать в долив.
        ask.rows, ask.ms, ask.err = ask_indexer(api.get_json, url, response_budget(name))
        ask.done.set()

    threading.Thread(target=work, daemon=True, name=f"idx-{name}").start()
    return ask
