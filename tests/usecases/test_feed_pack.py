"""Зеркально проверяет сценарии подачи и упаковки потока."""

from torrcast.usecases.feed_pack import Feed, Packer


def test_feed_pack_scenarios_are_importable() -> None:
    assert Feed is not None and Packer is not None
