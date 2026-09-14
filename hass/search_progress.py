"""Шаг ``POST /api/search`` с ``progressive: true``: список растёт по мере ответов (TC-1126).

Своих правил тут тоже нет, ровно как у :mod:`hass.searching` - только полный круг поиска
(:func:`~torrcast.usecases.discover.search_circle.search_circle`) идёт фоновым потоком, а
пока он не вернулся, ответ строится тем, что уже приехало прямо сейчас
(:meth:`~torrcast.adapters.prowlarr.prowlarr.Prowlarr.inflight`, шов ``on_indexer``
:func:`~torrcast.usecases.discover.search_circle.search_circle`). Опорных индексеров
(:mod:`torrcast.domain.wait_indexer`) это не касается: ждёт их по-прежнему сам круг,
превью лишь подглядывает в то, что он уже собрал, ничего не подгоняя и не обрывая.

Заход держится реестром по тексту запроса: повторный опрос той же вкладки не начинает
новый поиск, а подглядывает в уже идущий - иначе каждый опрос браузера раз в секунду
удваивал бы нагрузку на индексеры. Только опт-ин путь: без ``progressive`` в теле
запрос идёт прежним, однократным, блокирующим :func:`hass.searching.searching`, и
Home Assistant (единственный слепой к заголовкам вызывающий, ``SEARCH_REQUEST_TIMEOUT``
без опроса) этой ветки не видит вовсе.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from typing import TYPE_CHECKING

from hass import searching
from hass.catalog_merge import catalog_merge
from hass.catalog_tiles import CatalogTiles
from hass.refused_error import RefusedError
from hass.search_job import SearchJob, _Shared
from hass.search_results import _hit
from hass.searching import Detect, Offer, Remember
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.cluster import cluster
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.menu_order import menu_order
from torrcast.domain.pick_franchise import pick_franchise
from torrcast.domain.profile import Profile
from torrcast.domain.raw_result import RawResult
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.search_circle import search_circle

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan

#: Сколько готовый заход живёт в реестре: следующий опрос той же вкладки ещё застаёт
#: готовый ответ, а не начинает новый заход в сеть только потому, что человек обновил
#: страницу секундой позже.
JOB_TTL = 30.0

#: Полный круг поиска, но с ходом внутрь (:func:`search_circle`'s ``on_indexer``):
#: боевая сборка звонит настоящему кругу, подделка нужна только тестам.
ProgressiveSearch = Callable[
    [Config, "Args", Progress, Profile, Callable[[IndexerClient], None]], list["Plan"]
]


def _search_with_hook(
    config: Config,
    args: Args,
    said: Progress,
    profile: Profile,
    on_indexer: Callable[[IndexerClient], None],
) -> list[Plan]:
    """Боевой :data:`ProgressiveSearch`: тот же круг, что и у обычного поиска."""
    return search_circle(config, args, said, profile, on_indexer=on_indexer)


PROGRESSIVE_SEARCH: ProgressiveSearch = _search_with_hook


#: Заходы поиска по тексту запроса; общий на процесс, как и у прочих слотов моста.
_jobs: dict[str, SearchJob] = {}
_jobs_lock = threading.Lock()


def _preview(query: str, job: SearchJob, offer: Offer | None = None) -> list[JsonValue]:
    """Превью прямо сейчас: тем же разбором, что и полный круг, но по неполному пулу.

    Ступеней добора (второй язык, добор сезона и озвучки) тут нет нарочно: они сами
    платят заходами в сеть и решают об оригинале, а превью - только то, что уже
    ответило, без единого лишнего запроса к индексерам.
    """
    said = searching.OFFER if offer is None else offer
    if job.hits:
        return job.dress(job.hits, said)
    catalog = [] if job.catalog is None else job.catalog.tiles()
    shown = catalog_merge(catalog, _peek(query, job), done=False)
    return job.dress(shown, said) if shown else []


def _peek(query: str, job: SearchJob) -> list[JsonValue]:
    """Находки по тому, что клиент индексеров уже держит в руках."""
    peek = getattr(job.client, "inflight", None)
    raw: list[RawResult] = peek() if peek is not None else []
    if not raw:
        return []
    found = menu_order(pick_franchise(query, cluster(to_releases(raw))))
    return [_hit(picture, number, default=False) for number, picture in enumerate(found, start=1)]


def search_progress(
    config: Config,
    query: str,
    detect: Detect,
    remember: Remember,
    *,
    search: ProgressiveSearch = PROGRESSIVE_SEARCH,
    offer: Offer | None = None,
    warm: _Shared | None = None,
    catalog: Callable[[str], CatalogTiles] | None = None,
) -> tuple[list[JsonValue], bool]:
    """Тело ``POST /api/search`` с ``progressive: true``: превью или готовый список.

    Второе поле - «поиск ещё идёт», тем же смыслом, каким его несёт
    ``X-Torrcast-Partial`` у ``GET /api/card/*`` (:mod:`web.card_lookup`).

    🔴 Полнота готового ответа не отличается от обычного :func:`hass.searching.searching`
    ни на одну картину: круг внутри - тот же самый вызов :func:`~torrcast.usecases.
    discover.search_circle.search_circle`, только с одним лишним ходом внутрь. Превью
    промежуточных заходов на итог не влияет вовсе - оно только читает то, что круг уже
    собрал, и не подменяет собой ни одного его шага. ``warm`` - общий кэш кругов
    (:mod:`hass.search_job`): с ним выдача, прогрев и карточка платят один круг на запрос.
    ``catalog`` - плитки каталога под запрос (:mod:`hass.catalog_tiles`): они стоят на экране
    до первой раздачи, а без раздач гаснут только после полного круга.
    """
    key = query.strip().casefold()
    with _jobs_lock:
        job = _jobs.get(key)
        stale = job is not None and job.done and time.monotonic() - job.finished_at > JOB_TTL
        if job is None or stale:
            job = SearchJob(catalog=None if catalog is None else catalog(query))
            _jobs[key] = job
            threading.Thread(
                target=job.run,
                args=(config, query, detect, remember, search, offer, warm),
                daemon=True,
                name="search-progress",
            ).start()
    if not job.done:
        return _preview(query, job, offer), True
    if job.error is not None:
        raise RefusedError(job.error)
    return job.results, False


__all__ = ["JOB_TTL", "PROGRESSIVE_SEARCH", "ProgressiveSearch", "search_progress"]
