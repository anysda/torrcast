"""Проверяет диапазонный HTTP-адаптер без настоящей сети."""

import http.client
from typing import Any

import pytest

from torrcast.adapters.frames.http_range_reader import HttpRangeReader
from torrcast.domain.swarm_silent_error import SwarmSilentError


class _Answer:
    def __enter__(self) -> "_Answer":
        return self

    def __exit__(self, *_: Any) -> None:
        return None

    def read(self) -> bytes:
        return b"index"


def test_reads_requested_range_and_counts_cost() -> None:
    """Адаптер передаёт точный диапазон и сохраняет цену запроса."""
    asked: list[tuple[str, float]] = []

    def open_(request: Any, timeout: float) -> _Answer:
        asked.append((request.headers["Range"], timeout))
        return _Answer()

    reader = HttpRangeReader("https://example.test/movie.mkv", 17.0, open_)

    assert reader.read(10, 5) == b"index"
    assert asked == [("bytes=10-14", 17.0)]
    assert (reader.taken, reader.requests) == (5, 1)


def test_a_body_cut_short_is_named_a_silent_swarm() -> None:
    """Раздача закрыла поток на полуслове - это молчание роя, а не поломка прибора.

    Своё имя тут решает многое: ответ про рой не запоминается полкой карт, а сырое
    исключение ``http.client`` уехало бы мимо всех ловцов и уронило бы показ.
    """

    class _Torn(_Answer):
        def read(self) -> bytes:
            raise http.client.IncompleteRead(b"half", 4096)

    def open_(request: Any, timeout: float) -> _Torn:
        return _Torn()

    reader = HttpRangeReader("https://example.test/movie.mkv", 17.0, open_)
    with pytest.raises(SwarmSilentError, match="cannot read the head of the file"):
        reader.read(0, 4096)
    assert (reader.taken, reader.requests) == (0, 0), "оборванный кусок зачлись как взятый"
