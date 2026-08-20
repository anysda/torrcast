"""Ответ SPARQL в пары «IMDb, минуты»; зовёт адаптер Wikidata."""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Единица измерения Wikidata → сколько в ней минут. Длительность (P2047) - величина С
#: ЕДИНИЦЕЙ, и единица у неё не одна на всех: у большинства картин записаны минуты, но
#: встречаются и секунды. Раньше число бралось голым и всегда считалось минутами, а
#: стоило это строки, которую человек читает: у «Оппенгеймера» записаны 10809 секунд, и
#: карточка обещала «180 ч 9 мин» вместо трёх часов - в шестьдесят раз больше правды.
#: Хронометраж - один из двух признаков, по которым отличают картину от однофамильца,
#: и такое число подрывает доверие ко всей строке.
_UNITS: Final[dict[str, float]] = {"Q11574": 1 / 60, "Q7727": 1.0, "Q25235": 60.0}
#: Число как его отдаёт SPARQL: целое или десятичное, без знака.
_AMOUNT_RE: Final = re.compile(r"\d+(\.\d+)?")


def read_sparql(payload: JsonValue) -> dict[str, tuple[str, int]]:
    """Ответ SPARQL → ``{Q-идентификатор: (tt…, минуты)}``; чего нет — того нет.

    Единица приезжает своей ячейкой (``unit``) и приводит число к минутам
    (:data:`_UNITS`). Единицы в ответе нет или она незнакомая - число остаётся минутами:
    так записано у большинства картин, и это ровно прежнее поведение.
    """
    out: dict[str, tuple[str, int]] = {}
    if not isinstance(payload, dict):
        return {}
    rows = json_rows(json_map(payload.get("results")).get("bindings"))
    for row in rows:
        cells = json_map(row)
        item = str(json_map(cells.get("item")).get("value", "")).rsplit("/", 1)[-1]
        if not item.startswith("Q"):
            continue
        imdb = str(json_map(cells.get("imdb")).get("value", ""))
        raw = str(json_map(cells.get("dur")).get("value", ""))
        unit = str(json_map(cells.get("unit")).get("value", "")).rsplit("/", 1)[-1]
        amount = float(raw) if _AMOUNT_RE.fullmatch(raw) else 0.0
        out[item] = (imdb, round(amount * _UNITS.get(unit, 1.0)))
    return out
