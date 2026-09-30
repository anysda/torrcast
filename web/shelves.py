"""``GET /api/shelves``: полки «Новинки»/«Популярное» из серверного кэша, без сети."""

from __future__ import annotations

import json

from hass.hit_posters import hits
from hass.shelf_posters import ShelfPosters
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.torrent_catalogue import torrent_catalogue
from torrcast.domain.feed_row import FeedRow
from torrcast.runtime.facts_wiring import FACTS
from web.answer import Answer
from web.request import Request
from web.shelf_playable import PLAYABLE
from web.shelves_cache import ShelvesCache
from web.warm_wiring import TARGETS


def _playable(query: str, key: str) -> bool | None:
    """Плитка играет, если фоновый отбор раздачи нашёл рабочую дорожку (TC-1343).

    Трёхсоставный приговор (:data:`web.shelf_playable.Verdict`) идёт наружу как есть -
    «не знаю» решает :func:`web.shelf_tiles._covered`, не эта проводка.
    """
    return PLAYABLE.of(query, key, load_config())


def _feed(limit: int) -> list[FeedRow]:
    """Лента Prowlarr по настройкам с диска - читаются они тут, а не при импорте модуля.

    Импорт этого файла идёт при каждом запуске тестов веб-слоя (:mod:`web.routes`), и
    чтение файла настроек прямо при импорте роняло бы их все на голой машине без
    Prowlarr. Читает их только фоновый цикл кэша: живой запрос страницы конфиг не
    спрашивает ни разу (TC-1110).
    """
    settings = load_config()
    return Prowlarr(settings.prowlarr_url, settings.prowlarr_apikey).feed(limit)


#: Обложки холодного захода полок: путь видимой выдачи поиска, байты по мере приезда.
_POSTERS = ShelfPosters(hits)

#: Кэш полок процесса - один на весь юнит показа; фон встаёт со службой (:mod:`web.warm_saved`),
#: а не при импорте (см. :func:`_feed`). Холодный заход показывает плитки до приговоров.
_cache = ShelvesCache(
    feed=_feed,
    catalogue=torrent_catalogue,
    offer=hits.settled,
    passport=FACTS.passport.of,
    playable=_playable,
    warm=TARGETS.prepare,
    ask=_POSTERS.ask,
    landed=_POSTERS.landed,
    arriving=_POSTERS.arriving,
    # Одна рука, как прежде: плитки и так видны до приговоров, а три руки кончали не раньше
    # (темп задают TorrServer и сеть) и отнимали у запуска показа метаданные раздачи.
    workers=1,
    early=True,
)


#: Заголовок, которым ответ метится, пока фон ни разу не собрал полки (``built_at``
#: пуст): та же метка недоехавшего ответа, что и у карточки (:mod:`web.card`) -
#: страница по ней переспрашивает сама, и открытая на холодном старте вкладка полки
#: дожидается без перезагрузки.
_PARTIAL = "X-Torrcast-Partial"
#: Полки уже видны, но приговоры «играет ли» ещё идут (:mod:`web.shelf_pass`): плитка,
#: которая не играет, сойдёт, и её место займёт следующая - страница переспрашивает реже.
_SETTLING = "X-Torrcast-Settling"


def shelves(_request: Request) -> Answer:
    """Полки как тело ``GET /api/shelves``; вся логика - в :class:`web.shelves_cache.ShelvesCache`.

    Доводов запроса нет: обе полки видит любой зашедший на главный экран одинаково.
    """
    said = _cache.get()
    body = json.dumps(said, ensure_ascii=False).encode("utf-8")
    extra: list[tuple[str, str]] = []
    if said.get("built_at") is None or _cache.filling:
        extra.append((_PARTIAL, "1"))
    if _cache.settling:
        extra.append((_SETTLING, "1"))
    return Answer(200, body, extra=tuple(extra))


__all__ = ["shelves"]
