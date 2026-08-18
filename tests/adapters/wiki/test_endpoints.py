"""Проверяет адреса источников справки."""

from torrcast.adapters.wiki import endpoints


def test_both_sources_are_named_by_host_and_path() -> None:
    """Русская Википедия и Wikidata - два разных хоста с разными точками входа."""
    assert endpoints.WIKI_HOST == "ru.wikipedia.org"
    assert endpoints.WIKI_PATH == "/w/api.php"
    assert endpoints.WIKIDATA_HOST == "query.wikidata.org"
    assert endpoints.WIKIDATA_PATH == "/sparql"


def test_sparql_is_asked_for_json_by_the_accept_header() -> None:
    """Без этого заголовка Wikidata отвечает разметкой, а не результатом."""
    assert endpoints.SPARQL_HEAD["Accept"] == "application/sparql-results+json"
