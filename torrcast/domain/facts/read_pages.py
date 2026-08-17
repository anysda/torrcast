"""Кандидат в статью, статья в описание; зовёт добор справки к меню."""

from __future__ import annotations

from typing import Any

from torrcast.domain.facts.confirms import confirms
from torrcast.domain.facts.wiki_reply import _article, _pages


def _read_pages(
    payload: Any, candidates: dict[tuple[str, int | None], list[str]]
) -> tuple[dict[tuple[str, int | None], str], dict[tuple[str, int | None], str]]:
    """Разобрать ответ Википедии: кандидат → статья → описание и Q-идентификатор.

    Запрошенное имя и заголовок статьи — не одно и то же: API нормализует регистр и ведёт
    по перенаправлениям, и «Моана (мультфильм)» вполне может ответить статьёй с другим
    заголовком. Обратный путь API отдаёт сам, списками ``normalized`` и ``redirects``.
    """
    hops, pages = _pages(payload)
    about: dict[tuple[str, int | None], str] = {}
    entities: dict[tuple[str, int | None], str] = {}
    for key, names in candidates.items():
        for name in names:
            page = _article(name, hops, pages)
            if page is None:
                continue
            extract = page.get("extract") or ""
            if not confirms(extract, key[1]):
                continue
            about[key] = extract
            props = page.get("pageprops") or {}
            if props.get("wikibase_item"):
                entities[key] = props["wikibase_item"]
            break
    return about, entities
