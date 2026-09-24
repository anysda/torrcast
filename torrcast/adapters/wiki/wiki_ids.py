"""Добирает IMDb-идентификатор и длительность сущностей Wikidata."""

from torrcast.adapters.wiki.endpoints import SPARQL_HEAD, WIKIDATA_HOST, WIKIDATA_PATH
from torrcast.domain.facts.read_sparql import read_sparql
from torrcast.ports.json_client import JsonClient


def wiki_ids(
    client: JsonClient, items: list[str], timeout: float, foreground: bool
) -> dict[str, tuple[str, int]]:
    """Q-идентификаторы → (идентификатор IMDb, минуты). Один запрос на все картины.

    Хронометраж берём здесь, а не из выгрузки IMDb, по цене вопроса: за ``title.basics``
    пришлось бы качать 225 МБ. Расхождение с IMDb бывает в пару минут - это разница в
    том, считать ли титры, а не выдумка.

    Длительность спрашивается ВМЕСТЕ С ЕДИНИЦЕЙ: ``wdt:`` отдаёт голое число, а
    величина у Wikidata с единицей; у большинства картин там минуты, у «Оппенгеймера»
    секунды, и без единицы разобрать одно от другого нечем. Единица лежит у значения
    утверждения (``psv:``), поэтому её приходится доставать отдельным шагом.

    Этот шаг - вложенный ``OPTIONAL`` внутри уже имеющегося: само число по-прежнему
    берётся у ``wdt:``, а единица лишь подсаживается к нему по равенству величины. Не
    нашлась - число остаётся минутами
    (:func:`torrcast.domain.facts.read_sparql.read_sparql`), как было.
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
