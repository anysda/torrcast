"""Зеркально проверяет сценарии подачи и упаковки потока."""

from torrcast.usecases.feed_pack import Feed, configure


def test_feed_pack_scenarios_are_importable() -> None:
    assert Feed is not None and configure is not None
