"""Заголовок той же картины в связанной языковой Википедии; зовут справка и паспорт."""

from __future__ import annotations

from torrcast.domain.json_map import json_map
from torrcast.domain.json_rows import json_rows
from torrcast.domain.json_value import JsonValue


def linked_title(page: JsonValue) -> str:
    """Как та же картина подписана в чужой Википедии - ровно так, как записана там.

    Ссылка едет тем же запросом, что и сама статья (:func:`extract_params`), и стоит
    поэтому ноль. Уточнение в скобке («(film)», «(TV series)») тут НЕ отрезается: это
    часть адреса статьи, и без него второй запрос уедет мимо неё - в страницу значений
    или в пустоту. Отрезает его тот, кому нужно имя, а не адрес
    (:func:`~torrcast.domain.facts.english_title.english_title`).
    """
    links = json_rows(json_map(page).get("langlinks"))
    return str(json_map(links[0]).get("title") or "") if links else ""
