"""``GET /api/web/sources``: сколько источников включено, из серверного кэша, без сети.

Число нужно строке «Ищем в N источниках…» под полем поиска, пока идёт поиск (ТЗ §4.2) -
источник числа один и тот же список, что спрашивает сам круг поиска
(:class:`torrcast.adapters.prowlarr.indexer_roster.IndexerRoster`).
"""

from __future__ import annotations

import json

from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.prowlarr.indexer_roster import IndexerRoster
from torrcast.adapters.prowlarr.prowlarr_api import ProwlarrApi
from web.answer import Answer
from web.request import Request
from web.sources_cache import SourcesCache


def _count() -> int:
    """Число включённых индексеров по настройкам с диска - читаются они тут, а не при
    импорте модуля (см. довод у :func:`web.shelves._feed`: живой запрос страницы конфиг
    не спрашивает ни разу, TC-1110)."""
    settings = load_config()
    api = ProwlarrApi(settings.prowlarr_url, settings.prowlarr_apikey)
    return len(IndexerRoster(api).known())


#: Кэш числа источников процесса - один на весь юнит показа; фон встаёт при первом же
#: запросе, а не при импорте (см. :func:`_count`).
_cache = SourcesCache(count=_count)


def sources(_request: Request) -> Answer:
    """Число источников как тело ``GET /api/web/sources``.

    Доводов запроса нет: строку видит любой, кто набирает поиск, одинаково.
    """
    body = json.dumps({"count": _cache.get()}).encode("utf-8")
    return Answer(200, body)


__all__ = ["sources"]
