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
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING, Protocol

from hass import searching
from hass.catalog_merge import catalog_merge
from hass.catalog_tiles import CatalogTiles
from hass.redress import redress
from hass.refused_error import RefusedError
from hass.search_job import POSTERS_BY, SearchJob, _Shared
from hass.search_results import _hit
from hass.searching import Detect, Offer, Remember
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
from torrcast.domain.menu_order import menu_order
from torrcast.domain.profile import Profile
from torrcast.domain.raw_result import RawResult
from torrcast.ports.progress.progress import Progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.discover.named_round import NamedRound
from torrcast.usecases.discover.recognized_pick import recognized_pick
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


class _Covers(Protocol):
    """Что мост знает о картинках записей (:class:`hass.hit_posters.HitPosters`)."""

    def landed(self, record: JsonValue) -> bool: ...

    def pending(self, records: Sequence[JsonValue]) -> bool: ...

    def due(self, records: Sequence[JsonValue]) -> bool: ...


#: Заходы поиска по тексту запроса; общий на процесс, как и у прочих слотов моста.
_jobs: dict[str, SearchJob] = {}
_jobs_lock = threading.Lock()


def _preview(
    query: str, job: SearchJob, offer: Offer | None = None, *, done: bool = False
) -> list[JsonValue]:
    """Превью прямо сейчас: тем же разбором, что и полный круг, но по неполному пулу.

    Ступеней добора (второй язык, добор сезона и озвучки) тут нет нарочно: они сами
    платят заходами в сеть и решают об оригинале, а превью - только то, что уже
    ответило, без единого лишнего запроса к индексерам. ``done`` - это финал к сроку
    (:data:`~hass.search_job.FINAL_BY`): картины каталога без раздач тогда гаснут.
    """
    said = searching.OFFER if offer is None else offer
    if job.hits:
        return job.dress(job.hits, said)
    catalog = [] if job.catalog is None else job.catalog.tiles()
    shown = catalog_merge(catalog, _peek(query, job), done=done)
    return job.dress(shown, said) if shown else []


def _peek(query: str, job: SearchJob) -> list[JsonValue]:
    """Находки по тому, что клиент индексеров уже держит в руках."""
    peek = getattr(job.client, "inflight", None)
    raw: list[RawResult] = peek() if peek is not None else []
    named = job.client.named_inflight() if isinstance(job.client, NamedRound) else []
    if not raw and not named:
        return []
    known = job.client.known if isinstance(job.client, NamedRound) else None
    found = menu_order(recognized_pick(query, raw, named, known)[1])
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
    covers: _Covers | None = None,
) -> tuple[list[JsonValue], bool]:
    """Тело ``POST /api/search`` с ``progressive: true``: превью или готовый список.

    Второе поле - «поиск ещё идёт», как ``X-Torrcast-Partial`` у :mod:`web.card_lookup`.

    🔴 Полнота готового ответа не отличается от обычного :func:`hass.searching.searching`
    ни на одну картину: круг внутри - тот же самый вызов :func:`~torrcast.usecases.
    discover.search_circle.search_circle`, только с одним лишним ходом внутрь. Превью
    промежуточных заходов на итог не влияет вовсе - оно только читает то, что круг уже
    собрал, и не подменяет собой ни одного его шага. ``warm`` - общий кэш кругов
    (:mod:`hass.search_job`): с ним выдача, прогрев и карточка платят один круг на запрос.
    ``catalog`` - плитки каталога под запрос (:mod:`hass.catalog_tiles`): они стоят на экране
    до первой раздачи, а без раздач гаснут только после полного круга.

    Финал приходит не позже срока :data:`~hass.search_job.FINAL_BY` от начала захода: тот,
    кто опрашивает, получает к нему собранное, а круг досчитывается фоном.

    ``covers`` - память картинок моста. С ней имя картинки уходит только тем записям, чьи
    байты уже здесь: плитка, спросившая имя раньше байтов, держала соединение браузера до
    6 с, и шесть таких плиток останавливали опрос поиска (TC-1286). Отложенный из-за 429
    приговор готового списка спрашивается снова опросом, застав конец тишины, а заход с
    обложками в пути не сменяется новым кругом до :data:`~hass.search_job.POSTERS_BY`.
    """
    key = query.strip().casefold()
    with _jobs_lock:
        job = _jobs.get(key)
        stale = job is not None and job.done and time.monotonic() - job.finished_at > JOB_TTL
        stale = stale and not (job is not None and _coming(job, covers))
        if job is None or stale:
            job = SearchJob(catalog=None if catalog is None else catalog(query))
            _jobs[key] = job
            threading.Thread(
                target=job.run,
                args=(config, query, detect, remember, search, offer, warm),
                daemon=True,
                name="search-progress",
            ).start()
    if job.overdue():
        job.settle(_preview(query, job, offer, done=True))
    if not job.done:
        preview = _preview(query, job, offer)
        return (preview if covers is None else _shown(preview, covers)), True
    if job.error is not None:
        raise RefusedError(job.error)
    if covers is None:
        return job.results, False
    job.promised = job.promised or covers.pending(job.results)
    if _coming(job, covers) and not job.judging and covers.due(job.results):
        redress(job, searching.OFFER if offer is None else offer)
    return _shown(job.results, covers), False


def _coming(job: SearchJob, covers: _Covers | None) -> bool:
    """Обложки готового захода в пути или были в пути у опроса, и потолок не пройден."""
    if covers is None or not job.done or time.monotonic() - job.started_at >= POSTERS_BY:
        return False
    return job.promised or job.judging or covers.pending(job.results)


def _shown(results: list[JsonValue], covers: _Covers) -> list[JsonValue]:
    """Записи для страницы: имя картинки только у тех, чьи байты уже здесь."""
    return [
        {name: value for name, value in record.items() if name != "poster"}
        if isinstance(record, dict) and "poster" in record and not covers.landed(record)
        else record
        for record in results
    ]


__all__ = ["JOB_TTL", "PROGRESSIVE_SEARCH", "ProgressiveSearch", "search_progress"]
