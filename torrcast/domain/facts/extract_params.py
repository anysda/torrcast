"""Параметры запроса к API Википедии за первыми фразами статей; зовёт адаптер справки."""

from __future__ import annotations

from torrcast.domain.facts.settings import _EXCHARS, _EXLIMIT


def extract_params(names: list[str]) -> dict[str, str]:
    """Один запрос за первыми фразами сразу нескольких статей и их Q-идентификаторами."""
    return {
        "action": "query",
        "titles": "|".join(names[:_EXLIMIT]),
        "redirects": "1",
        # Ссылка на английскую статью едет тем же запросом и ничего не стоит, а имя за ней
        # - ровно то, которым картину подписывают индексеры. Русская статья про аниме
        # оригинал латиницей не пишет вовсе («Юная революционерка Утэна» - и японские
        # иероглифы в скобке), и без этой ссылки добирать было бы нечем.
        "prop": "extracts|pageprops|langlinks",
        "lllang": "en",
        # Потолок общий на все статьи запроса, а не на каждую: с ``1`` ссылка приезжала бы
        # только у первой из них, и повезло бы не тому кандидату.
        "lllimit": str(_EXLIMIT),
        "ppprop": "disambiguation|wikibase_item",
        "exintro": "1",
        "explaintext": "1",
        "exchars": str(_EXCHARS),
        "exlimit": str(_EXLIMIT),
        "format": "json",
        "formatversion": "2",
    }
