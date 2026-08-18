"""Кандидат в статью, статья в описание; зовёт добор справки к меню."""

from __future__ import annotations

from torrcast.domain.facts.confirms import confirms
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def _read_pages(
    payload: JsonValue, candidates: dict[tuple[str, int | None], list[str]]
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
            if not confirms(extract, key[1]):
                continue
            about[key] = extract
            props = json_map(page.get("pageprops"))
            if props.get("wikibase_item"):
                entities[key] = str(props["wikibase_item"])
            break
    return about, entities
