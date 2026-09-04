"""Род картины, который статья называет своими категориями; зовёт отбор статей постера.

Стоит это столько же, сколько и год оттуда же, - ноль лишних походов: категории
приезжают тем же запросом, что и сама статья.
"""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def page_kinds(page: JsonValue) -> set[str]:
    """Род картины по её категориям: «movie», «tv» или оба; неясно - пусто.

    Год один и тот же бывает у фильма и у сериала под одним именем: «Паразиты» 2019
    года - это и корейский фильм, и сериал, и без рода в список приезжали две строки с
    ОДНОЙ картинкой. Категория про род говорит тем же словом, что и про год, и стоит
    поэтому столько же - ноль.
    """
    out: set[str] = set()
    for row in json_rows(json_map(page).get("categories")):
        low = str(json_map(row).get("title", "")).casefold()
        if "сериал" in low or "television series" in low or "miniseries" in low:
            out.add("tv")
        elif "фильм" in low or "кино" in low or "film" in low:
            out.add("movie")
    return out
