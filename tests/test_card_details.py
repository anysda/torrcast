"""Мелкие расчёты полного тела карточки."""

from torrcast.domain.release import Release
from web.card_details import CardDetails


def test_the_details_count_each_named_indexer_once() -> None:
    releases = [Release(raw_name="one", title="One", indexer="a", indexers=("a", "b"))]

    assert CardDetails.sources_count(releases) == 2
