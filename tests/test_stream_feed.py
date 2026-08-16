"""Проверяет совместимый фасад подачи потока."""

import torrcast.stream_feed


def test_stream_feed_facade_is_importable() -> None:
    assert torrcast.stream_feed.Feed is not None
