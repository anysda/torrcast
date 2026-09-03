"""Годы, которые статья называет своими категориями; зовёт отбор статей постера.

Это самая дешёвая сверка года из всех: категории приезжают ТЕМ ЖЕ запросом, что и сама
статья, и стоят поэтому ноль лишних походов. Форма категории у русского раздела гуляет
(«Фильмы 2011 года», «Телесериалы США, запущенные в 2008 году», «Аниме 2003 года»), и
перечислить её заранее нельзя - поэтому год тут не спрашивается по имени категории, а
читается из любой, где стоит рядом со словом «год».
"""

from __future__ import annotations

import re
from typing import Final

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue

#: Год в имени категории. Слово «год» рядом обязательно: без него сюда попадали бы
#: «2001: Космическая одиссея» и прочие числа из названий, то есть годы чужих картин.
_YEAR_RE: Final = re.compile(r"\b(\d{4})\s+год")


def page_years(page: JsonValue) -> set[int]:
    """Годы из категорий статьи; год не назван ни одной - пустое множество.

    Пустота тут значит «сказать нечем», а не «год не тот»: у части статей года в
    категориях нет вовсе, и решает про них уже Wikidata
    (:class:`~torrcast.adapters.wiki.wikidata_years.WikidataYears`).
    """
    out: set[int] = set()
    for row in json_rows(json_map(page).get("categories")):
        for match in _YEAR_RE.finditer(str(json_map(row).get("title", ""))):
            out.add(int(match.group(1)))
    return out
