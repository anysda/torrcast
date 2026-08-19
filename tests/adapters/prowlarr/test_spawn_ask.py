"""Один спрошенный индексер: свой поток, свой личный срок и место под ответ."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from torrcast.adapters.prowlarr.spawn_ask import spawn_ask
from torrcast.domain.response_budget import response_budget


class _Http:
    """Подставной клиент: одна строка в ответ и память о том, с каким сроком спросили."""

    def __init__(self) -> None:
        self.asked: list[tuple[str, float]] = []

    def new_session(self) -> Any:
        return "сессия"

    def get_json(self, session: Any, url: str, timeout: float, base_url: str) -> Any:
        self.asked.append((url, timeout))
        return [
            {
                "title": "picture",
                "infoHash": "a" * 40,
                "size": 1024,
                "seeders": 5,
                "indexer": "idx",
            }
        ]

    def post(self, session: Any, url: str, body: Any, timeout: float) -> None:
        return None

    def probe(self, *args: Any) -> None:
        return None


def test_the_answer_lands_in_the_place_kept_for_it_not_in_the_call() -> None:
    """Круг уходит по опорным, поэтому ответ ложится в место, а вызов не ждёт его."""
    http = _Http()
    api = ProwlarrApi("http://p", "KEY", http=http)

    ask = spawn_ask(api, "матрица", 100, 1, "Knaben", budget=0.5)

    assert ask.done.wait(2.0), "закончив, поток обязан поднять флаг"
    assert (ask.name, ask.budget) == ("Knaben", 0.5)
    assert ask.rows is not None and len(ask.rows) == 1 and ask.err is None
    url, timeout = http.asked[0]
    assert url.endswith("&indexerIds=1"), "спрошен ровно тот индексер, которого назвали"
    assert timeout == response_budget("Knaben"), "запрос живёт личный срок, а не бюджет круга"
