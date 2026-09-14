"""Зеркало :mod:`torrcast.domain.facts.kin_batch_query`: SPARQL за родней пачки картин."""

from torrcast.domain.facts.kin_batch_query import kin_batch_query
from torrcast.domain.facts.kin_query import kin_query


def test_a_batch_asks_every_picture_by_the_same_three_branches() -> None:
    """Пачка родни - те же ветки, что у одиночного запроса, только над ``?src``."""
    query = kin_batch_query(["Q1", "Q2"])

    assert "VALUES ?src { wd:Q1 wd:Q2 }" in query
    assert "?src wdt:P179" in query
    assert "?item wdt:P179/wdt:P361* ?src" in query
    assert "FILTER(?item != ?src)" in query
    single = kin_query("Q7").replace("wd:Q7", "?src").split("WHERE {", 1)[1]
    assert query.endswith(single), "ветки пачки разошлись с одиночным запросом"
