"""Кандидат в статью, статья в описание; зовёт добор справки к меню."""

from __future__ import annotations

from collections.abc import Set

from torrcast.domain.facts.confirms import confirms
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def _read_pages(
    payload: JsonValue,
    candidates: dict[tuple[str, int | None], list[str]],
    confirmed: Set[tuple[str, int | None]] = frozenset(),
) -> tuple[dict[tuple[str, int | None], str], dict[tuple[str, int | None], str]]:
    """Разобрать ответ Википедии: кандидат → статья → описание и Q-идентификатор.

    Запрошенное имя и заголовок статьи — не одно и то же: API нормализует регистр и ведёт
    по перенаправлениям, и «Моана (мультфильм)» вполне может ответить статьёй с другим
    заголовком. Обратный путь API отдаёт сам, списками ``normalized`` и ``redirects``.
    """
    hops, pages = wiki_pages(payload)
    about: dict[tuple[str, int | None], str] = {}
    entities: dict[tuple[str, int | None], str] = {}
    for key, names in candidates.items():
        for name in names:
            page = _article(name, hops, pages)
            if page is None:
                continue
            extract = str(page.get("extract") or "")
            # Некоторые точные статьи не называют год в первых 500 символах. Тогда
            # пару имени, года и типа вправе подтвердить офлайн-карта IMDb. Послабление
            # действует только для полного имени: отрезанное до двоеточия имя легко
            # оказалось бы другой частью той же франшизы.
            exact = key in confirmed and name.casefold() == key[0].strip().casefold()
            if not confirms(extract, key[1]) and not exact:
                continue
            about[key] = extract
            props = json_map(page.get("pageprops"))
            if props.get("wikibase_item"):
                entities[key] = str(props["wikibase_item"])
            break
    return about, entities
