"""Строка SPARQL за родней пачки картин по их Q-идентификаторам; зовёт адаптер Wikidata."""

from __future__ import annotations

from torrcast.domain.facts.kin_query import _branches


def kin_batch_query(entities: list[str]) -> str:
    """Та же родня пачкой картин: те же ветки, а ``?src`` говорит, чья это строка.

    Q-коды плиток полки приходят с самой полкой, и родня каждой спрашивается заранее,
    до наведения. По одному запросу это 1-2 с на плитку; пачка из 25 - 2.6-8.6 с на всю
    пачку (замер CT501 14-09-2026), и множества родни у каждой совпали с одиночными.
    """
    values = " ".join(f"wd:{entity}" for entity in entities)
    head = f"SELECT ?src ?item ?itemLabel ?itemLabelRu ?date WHERE {{ VALUES ?src {{ {values} }} "
    return head + _branches("?src")
