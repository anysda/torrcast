"""Прогрев видимого идёт к индексерам фоном, карточка и живой поиск - нет."""

from __future__ import annotations

from collections.abc import Callable

from torrcast.adapters.prowlarr.host_slots import HOST_SLOTS
from torrcast.adapters.prowlarr.warmup import WARMUP
from torrcast.usecases.select.plan import Plan
from web.warm_cache import WarmCache


def _sync(job: Callable[[], None]) -> None:
    job()


def test_the_screens_warmup_is_counted_as_warmup_and_the_card_is_not() -> None:
    seen: dict[str, bool] = {}

    def circle(query: str) -> list[Plan]:
        seen[query] = WARMUP.get()
        return []

    cache = WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=_sync)
    cache.ask(["тачки"])
    cache.hint("наруто")
    cache.take("интерстеллар")
    assert seen == {"тачки": True, "наруто": False, "интерстеллар": False}


def test_a_live_search_holds_the_adapters_queues_while_it_counts() -> None:
    live: list[int] = []

    def circle(_query: str) -> list[Plan]:
        live.append(HOST_SLOTS._live)
        return []

    WarmCache(circle=circle, blurbs=lambda _pictures: None, spawn=_sync).take("тачки")
    assert live == [1], "the adapter did not know a viewer searched"
    assert HOST_SLOTS._live == 0, "the live search ended and still held the warmup"
