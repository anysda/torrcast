"""Добирает IMDb-идентификатор и длительность сущностей Wikidata."""

from torrcast.adapters.wiki.endpoints import SPARQL_HEAD, WIKIDATA_HOST, WIKIDATA_PATH
from torrcast.domain.facts.read_sparql import read_sparql
from torrcast.ports.json_client import JsonClient


def wiki_ids(
    client: JsonClient, items: list[str], timeout: float, foreground: bool
) -> dict[str, tuple[str, int]]:
    """Q-идентификаторы → (идентификатор IMDb, минуты). Один запрос на все картины.

    Длительность спрашивается вместе с единицей: у большинства картин там минуты, у
    «Оппенгеймера» секунды. Вложенный ``OPTIONAL`` достаёт единицу по тому же числу, а
    без неё число остаётся минутами (:func:`torrcast.domain.facts.read_sparql.read_sparql`).
    """
    values = " ".join(f"wd:{item}" for item in items)
    query = (
        f"SELECT ?item ?imdb ?dur ?unit WHERE {{ VALUES ?item {{ {values} }} "
        "OPTIONAL { ?item wdt:P345 ?imdb } "
        "OPTIONAL { ?item wdt:P2047 ?dur . "
        "OPTIONAL { ?item p:P2047/psv:P2047 ?value . "
        "?value wikibase:quantityAmount ?dur ; wikibase:quantityUnit ?unit } } }"
    )
    payload = client.get(
        WIKIDATA_HOST,
        WIKIDATA_PATH,
        {"query": query},
        dict(SPARQL_HEAD),
        timeout,
        foreground=foreground,
    )
    return read_sparql(payload)
