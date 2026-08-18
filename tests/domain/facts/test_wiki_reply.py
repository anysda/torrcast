"""Зеркало :mod:`torrcast.domain.facts.wiki_reply`: склейка ответов в один разбор."""

from typing import Any

from torrcast.domain.facts.wiki_reply import _merged
from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows


def test_answers_of_several_batches_merge_into_one() -> None:
    """Разбор кандидатов о пакетах знать не должен: склеиваются все три списка."""
    one: dict[str, Any] = {"query": {"pages": [{"title": "Тачки"}], "normalized": []}}
    two: dict[str, Any] = {
        "query": {"pages": [{"title": "Моана"}], "redirects": [{"from": "а", "to": "б"}]}
    }
    merged = _merged([one, two, "не словарь"])
    query = json_map(merged["query"])
    assert [json_map(page)["title"] for page in json_rows(query["pages"])] == ["Тачки", "Моана"]
    assert query["redirects"] == [{"from": "а", "to": "б"}]
