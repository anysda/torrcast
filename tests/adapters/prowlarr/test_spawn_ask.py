"""Один спрошенный индексер: свой поток, свой личный срок и место под ответ."""

from __future__ import annotations

import threading
from typing import Any

import pytest

from torrcast.adapters.prowlarr import spawn_ask as spawn_ask_module
from torrcast.adapters.prowlarr.down_book import DOWN_BOOK
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


def test_a_zero_at_the_adapters_cut_is_a_silence_and_a_quick_one_an_answer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """JacRed's adapter gives up at 5 s with an empty list: three in a row make it down."""
    api = ProwlarrApi("http://p", "KEY", http=_Http())
    answer: list[tuple[list[Any], int, None]] = [([], 5012, None)]
    monkeypatch.setattr(spawn_ask_module, "ask_indexer", lambda *_args: answer[0])
    for _ in range(3):
        _ask(api, "JacRed")
    assert DOWN_BOOK.down() == {"JacRed"}, "an empty list at the cut is no answer"
    answer[0] = ([], 300, None)
    _ask(api, "JacRed")
    assert DOWN_BOOK.down() == frozenset(), "a quick zero is an honest answer and brings it back"


def _ask(api: ProwlarrApi, name: str) -> None:
    ask = spawn_ask(api, "матрица", 100, 4, name, budget=0.5)
    assert ask.done.wait(2.0)
    for thread in threading.enumerate():
        if thread.name == f"idx-{name}":
            thread.join(2.0)
