"""Адрес картинки из ответа ``imageinfo``; зовёт адаптер постера."""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def poster_address(payload: JsonValue) -> str:
    """Ответ ``imageinfo`` → адрес файла; сначала уменьшенная копия, потом оригинал.

    Уменьшенная копия стоит первой не ради трафика, а ради самой картинки: постеры
    бывают векторными (у «Уэнздей» в инфобоксе логотип ``.svg``), а карточка плеера
    вектор не рисует - ``iiurlwidth`` отдаёт его растром. Оригинал остаётся запасным
    ответом: у него тот же формат, что лежит на складе, и ужимать его некому.
    """
    query = json_map(json_map(payload).get("query"))
    for page in json_rows(query.get("pages")):
        for info in json_rows(json_map(page).get("imageinfo")):
            row = json_map(info)
            address = str(row.get("thumburl") or row.get("url") or "")
            if address:
                return address
    return ""
