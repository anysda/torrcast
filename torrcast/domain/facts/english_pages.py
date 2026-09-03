"""Адреса тех же картин в английской Википедии; зовёт адаптер постера."""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.facts.linked_title import linked_title
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_value import JsonValue


def english_pages(payload: JsonValue, names: Iterable[str]) -> list[str]:
    """Ответ русской Википедии → адреса английских статей, в порядке спрошенных имён.

    Спрашивается сразу вся очередь имён картины (:func:`titles_for`), и ответов бывает
    несколько: у «Брата» голое имя ведёт в статью про родство (английское ``Brother``), а
    фильм лежит под «Брат (фильм, 1997)» и отвечает ``Brother (1997 film)``. Поэтому тут
    не «первый попавшийся», а СПИСОК в порядке доверия: инфобокс с постером есть у
    фильма, и у статьи про родство его нет, - выбор делает тот, кто читает инфобокс
    (:class:`~torrcast.adapters.wiki.wiki_poster.WikiPoster`), а не этот разбор.

    Страницу значений и пустышку в список не пускает :func:`_article`: у «Начала» и
    «Сталкера» голое имя - именно она, и межъязыковая ссылка с неё ведёт в такую же
    страницу значений английского раздела.
    """
    hops, pages = wiki_pages(payload)
    out: list[str] = []
    for name in names:
        page = _article(name, hops, pages)
        if page is None:
            continue
        address = linked_title(page)
        if address and address not in out:
            out.append(address)
    return out
