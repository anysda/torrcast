"""``GET /api/shelves``: полки «Новинки»/«Популярное» из серверного кэша, без сети."""

from __future__ import annotations

import json

from hass.hit_posters import hits
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from web.answer import Answer
from web.request import Request
from web.shelves_cache import ShelvesCache


def _feed(limit: int) -> list[FeedRow]:
    """Лента Prowlarr по настройкам с диска - читаются они тут, а не при импорте модуля.

    Импорт этого файла идёт при каждом запуске тестов веб-слоя (:mod:`web.routes`), и
    чтение файла настроек прямо при импорте роняло бы их все на голой машине без
    Prowlarr. Читает их только фоновый цикл кэша: живой запрос страницы конфиг не
    спрашивает ни разу (TC-1110).
    """
    settings = load_config()
    return Prowlarr(settings.prowlarr_url, settings.prowlarr_apikey).feed(limit)


#: Кэш полок процесса - один на весь юнит показа; фон встаёт при первом же запросе,
#: а не при импорте (см. :func:`_feed`).
_cache = ShelvesCache(feed=_feed, catalogue=torrent_catalogue, offer=hits.offer)


def shelves(_request: Request) -> Answer:
    """Полки как тело ``GET /api/shelves``; вся логика - в :class:`web.shelves_cache.ShelvesCache`.

    Доводов запроса нет: обе полки видит любой зашедший на главный экран одинаково.
    """
    body = json.dumps(_cache.get(), ensure_ascii=False).encode("utf-8")
    return Answer(200, body)


__all__ = ["shelves"]
