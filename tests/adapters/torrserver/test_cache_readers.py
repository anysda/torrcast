"""Число читателей раздачи берётся из ``Readers`` ответа ``/cache``, отказ службы - ноль."""

from typing import Any

from torrcast.adapters.torrserver.cache_readers import cache_readers
from torrcast.domain.server_down_error import ServerDownError


def test_the_readers_of_the_cache_are_counted() -> None:
    asked: list[tuple[str, dict[str, Any]]] = []

    def post(path: str, body: dict[str, Any]) -> Any:
        asked.append((path, body))
        return {"Hash": "abc", "Readers": [{"Start": 1, "End": 9, "Reader": 2}, {"Reader": 5}]}

    assert cache_readers(post, "abc") == 2
    assert asked == [("/cache", {"action": "get", "hash": "abc"})]


def test_a_closed_cache_or_a_missing_torrent_holds_nobody() -> None:
    def missing(_path: str, _body: dict[str, Any]) -> Any:
        raise ServerDownError("404")

    assert cache_readers(lambda _p, _b: {}, "abc") == 0
    assert cache_readers(lambda _p, _b: {"Readers": None}, "abc") == 0
    assert cache_readers(missing, "abc") == 0
