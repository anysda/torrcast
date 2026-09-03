"""Английские статьи с тем, чем сверяется их год; зовёт отбор статей постера.

Одних адресов тут мало. Справке хватало их: она читает описание, а описание тёзки видно
человеку как описание тёзки. Постеру не хватает - картинка чужой картины подписана НАШЕЙ
строкой, и отличить её человеку нечем. Поэтому вместе с адресом уносится и то, чем
статья сверяется: годы и род из её категорий и идентификатор картины в Wikidata.
"""

from __future__ import annotations

from collections.abc import Iterable

from torrcast.domain.facts.dated import Dated
from torrcast.domain.facts.linked_title import linked_title
from torrcast.domain.facts.named_year import named_year
from torrcast.domain.facts.page_kinds import page_kinds
from torrcast.domain.facts.page_years import page_years
from torrcast.domain.facts.wiki_pages import wiki_pages
from torrcast.domain.facts.wiki_reply import _article
from torrcast.domain.json_map import json_map
from torrcast.domain.json_value import JsonValue


def dated_pages(
    payload: JsonValue, names: Iterable[str] | None, linked: bool = True
) -> list[Dated]:
    """Ответ Википедии → статьи в порядке доверия, каждая со своей сверкой года.

    ``names`` перечисляет спрошенные имена и задаёт порядок; ``None`` означает, что
    статьи выбрал сам поиск Википедии, и порядок его же - тогда берутся все статьи
    ответа подряд. ``linked`` различает два раздела: у русского ответа межъязыковая
    ссылка кладётся в ``page``, а сама русская статья - в ``source``; у английского
    ответа статья и есть искомая, и русской половины у неё нет.

    🔴 Межъязыковая ссылка тут больше НЕ пропуск. Русская статья без английской пары
    раньше выбрасывалась целиком, а постер у неё есть свой: так терялись картинки
    ровно тех картин, про которые английский раздел статьи не завёл. Год у такой
    статьи сверяется тем же способом - категориями и Wikidata.

    Год берётся из СПРОШЕННОГО имени, а не только из того, куда оно привело: русский
    раздел держит «Паразиты (фильм, 2019)» перенаправлением на «Паразиты (фильм)», и
    само существование такого перенаправления и есть подтверждение года.

    Страницу значений и пустышку не пропускает :func:`_article`: у «Начала» и
    «Сталкера» голое имя - именно она, и ссылка с неё ведёт в такую же страницу
    значений английского раздела.
    """
    hops, pages = wiki_pages(payload)
    asked = list(names) if names is not None else list(pages)
    out: list[Dated] = []
    seen: set[tuple[str, str]] = set()
    for name in asked:
        page = _article(name, hops, pages)
        if page is None:
            continue
        native = str(page.get("title") or "")
        address = linked_title(page) if linked else native
        source = native if linked else ""
        if not (address or source) or (address, source) in seen:
            continue
        seen.add((address, source))
        entity = str(json_map(page.get("pageprops")).get("wikibase_item") or "")
        named = named_year(name) or named_year(native)
        years = page_years(page) | ({named} if named else set())
        out.append(Dated(address, entity, frozenset(years), frozenset(page_kinds(page)), source))
    return out
