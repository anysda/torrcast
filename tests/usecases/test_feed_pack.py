"""Зеркально проверяет сценарии подачи и упаковки потока."""

from torrcast.usecases.feed_pack.configure import configure
from torrcast.usecases.feed_pack.feed import Feed


def test_feed_pack_scenarios_are_importable() -> None:
    assert Feed is not None and configure is not None
