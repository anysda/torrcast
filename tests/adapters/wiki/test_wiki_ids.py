"""Проверяет пакетный добор IMDb-идентификаторов из Wikidata."""

from tests.fakes.json_client import FakeJsonClient
from torrcast.adapters.wiki.wiki_ids import wiki_ids


def test_the_duration_query_keeps_the_measured_price_of_the_alternative() -> None:
    reason = " ".join((wiki_ids.__doc__ or "").split())

    assert "за ``title.basics`` пришлось бы качать 225 МБ" in reason
    assert "Расхождение с IMDb бывает в пару минут" in reason
    assert "без единицы разобрать одно от другого нечем" in reason


def test_the_card_class_reaches_the_wikidata_duration_query() -> None:
    """После статьи карта не теряет приоритет на последнем источнике справки."""
    client = FakeJsonClient(lambda _host, _path, _params: {"results": {"bindings": []}})

    assert wiki_ids(client, ["Q1"], 1.0, foreground=True) == {}
    assert client.foregrounds == [True]
