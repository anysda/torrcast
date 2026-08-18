"""Тёзка того же года среди статей ответа; зовёт разбор паспорта."""

from __future__ import annotations

from collections.abc import Sequence

from torrcast.domain.facts.article_gate import _about_cinema
from torrcast.domain.facts.picture_year import picture_year
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def namesake(pages: Sequence[JsonValue], heading: str, year: int | None) -> str:
    """Заголовок ДРУГОЙ картины того же года, которую справка знает под тем же именем.

    🔴 TC-371. Двусмысленность бывает не в отборе, а в самих источниках: именем «Девять» и
    годом 2009 в русском прокате подписаны две разные картины - мюзикл (``Nine``) и
    мультфильм (``9``). Каталог сводит их в одну кучку: имя и год - оба признака отбора - у
    них совпадают, а больше в раздачах не сказано ничего. Развести их разбором нечем, и
    молчать об этом нельзя: человек просит «девять», получает одну из двух, и объяснения
    нет ни строчки.

    Признак стоит ровно ноль: статьи уже приехали. Справка спрашивается сразу под всеми
    уточнениями (:data:`_QUALIFIERS`), «(мультфильм)» и «(фильм)» среди них, и обе картины
    лежат в одном ответе - остаётся их сосчитать.

    Ограждения два, и оба про то, чтобы строка не стала шумом:

    * год ОДИН И ТОТ ЖЕ. Одноимённых картин в справке полно («Дюна» 1984 и 2021, «Моана»
      2016 и 2026), но год их разводит, и разводит его же отбор - говорить не о чем;
    * статья ДРУГАЯ: тот же заголовок приезжает по нескольку раз, потому что под разными
      уточнениями лежит одно перенаправление.

    Про кино ли вторая статья, решает тот же гейт, что и для первой (:func:`_about_cinema`):
    у «Матрицы» под тем же именем лежит таблица, и картиной она не станет.
    """
    if year is None:
        return ""
    for page in pages:
        if page is None:
            continue
        article = json_map(page)
        other = str(article.get("title") or "")
        extract = str(article.get("extract") or "")
        if other == heading or not _about_cinema(other, extract):
            continue
        if picture_year(extract) == year:
            return other
    return ""
