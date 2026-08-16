"""Проверяет диапазонный HTTP-адаптер без настоящей сети."""

from typing import Any

from torrcast.adapters.frames.http_range_reader import HttpRangeReader


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
