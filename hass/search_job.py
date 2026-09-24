"""Один фоновый заход прогрессивного поиска: круг, память показанного и приговор обложек.

Круг идёт через общий кэш кругов (:class:`web.warm_cache.WarmCache`), если он назван: тогда
поиск, прогрев выдачи, карточка и «похожие» платят за запрос ОДИН круг. Раньше выдача
считала свой круг мимо кэша, и первая же плитка той же выдачи гнала его второй раз.

Готовые записи собирает :func:`hass.search_results.search_results` - тем же вызовом, что
и у :func:`hass.searching.searching`: своей копии сборки записей заход раньше не звал
(TC-1329), а без общего вызова перестановка смотренного доехала бы только до одной дороги.
"""

from __future__ import annotations

import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Final, Protocol

from hass import searching
from hass.catalog_merge import catalog_merge
from hass.catalog_tiles import CatalogTiles
from hass.search_poster_verdict import SearchPosterVerdict
from hass.search_results import search_results
from hass.searching import Detect, Offer, Remember
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.goal_spare import GOAL
from torrcast.domain.json_value import JsonValue
from torrcast.domain.nothing_found_error import NothingFoundError
from torrcast.domain.profile import Profile
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.slot import progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.enter_take import enter_take

if TYPE_CHECKING:
    from torrcast.domain.args import Args
    from torrcast.usecases.select.plan import Plan

#: Срок финала от начала захода, секунды: цель самого круга (:data:`GOAL`) и две секунды на
#: приговор обложек. Приговор шёл после круга без срока, 8-10.5 с при нуле обложек на стенде,
#: и финал «Начало» ехал 18-21 с. К сроку опрос получает финал из собранного, круг и
#: приговор досчитываются фоном, и повторный заход застаёт их полный список.
FINAL_BY: Final = GOAL + 2.0
#: Потолок дозапроса обложек от начала захода, секунды: после финала страница спрашивает
#: обложки, пока они в пути, но не дольше него, а заход с обложками в пути не сменяется новым.
POSTERS_BY: Final = 60.0

#: Тот же тип, что :data:`hass.search_progress.ProgressiveSearch`; назван тут, чтобы не
#: замыкать импорт по кругу.
_Search = Callable[
    [Config, "Args", Progress, Profile, Callable[[IndexerClient], None]], "list[Plan]"
]


class _Shared(Protocol):
    """Общий кэш кругов: один круг на запрос для всех, кто его спросил."""

    def take(self, query: str, circle: Callable[[str], list[Plan]] | None = None) -> list[Plan]: ...


@dataclass
class SearchJob(SearchPosterVerdict):
    """Один фоновый поиск: клиент индексеров, как только он появился, и итог."""

    client: IndexerClient | None = None
    done: bool = False
    error: str | None = None
    results: list[JsonValue] = field(default_factory=list)
    finished_at: float = 0.0
    posters: dict[str, JsonValue] = field(default_factory=dict)
    #: A poll has seen this job's covers coming: the job then stays until the poster cap.
    promised: bool = False
    #: The finished circle's list before its poster verdict: previews show it at once.
    hits: list[JsonValue] = field(default_factory=list)
    #: Картины каталога под этот запрос (:mod:`hass.catalog_tiles`); без них - только раздачи.
    catalog: CatalogTiles | None = None
    started_at: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)
    #: One poster verdict of the job at a time: the source marks a picture only once it answers.
    _verdict: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def run(
        self,
        config: Config,
        query: str,
        detect: Detect,
        remember: Remember,
        search: _Search,
        offer: Offer | None = None,
        warm: _Shared | None = None,
    ) -> None:
        """Досчитать заход до конца: готовый список или слово отказа."""
        args = parse_args([query])
        chosen = detect(config)

        def circle(_query: str) -> list[Plan]:
            tuned = tune(config, chosen.profile)
            return search(tuned, args, progress(), chosen.profile, self._capture)

        try:
            plans = circle(query) if warm is None else warm.take(query, circle)
        except NothingFoundError:
            # Nothing found is an answer of the search, an empty list, not a failed search.
            plans = []
        except TorrcastError as refusal:
            # A named refusal is an answer too, and one the viewer is owed in words: the
            # circle knows WHY there is nothing (no releases with that season, the
            # franchise has no such part, nothing parsed out), and the empty screen says
            # none of it. Only the refusal with nothing to add above stays mute.
            plans, self.error = [], str(refusal)
        hits: list[JsonValue] = []
        if plans:
            named = [(plan.picture.key, _named(plan.picture)) for plan in plans]
            remember(args.title_query, named)
            taken = enter_take(plans, args.title_query).number
            hits = search_results(plans, taken)
        # Картины каталога без раздач гаснут только теперь, после полного круга.
        shown = (
            hits if self.catalog is None else catalog_merge(self.catalog.tiles(), hits, done=True)
        )
        if not shown:
            self.settle([], landed=True)
            return
        self.error = None
        # Publish the list only under the same lock that owns its poster verdict: a preview
        # either finished before this point or sees the final verdict already in progress.
        self._verdict.acquire()
        self.hits = shown
        try:
            # Имя обложки даёт тот же приговор, что и обычному поиску
            # (:data:`hass.searching.OFFER`): без этого шага веб-выдача шла совсем без
            # обложек. Отказ приговора выдачу не роняет.
            try:
                judged = (searching.OFFER if offer is None else offer)(shown)
            except (TorrcastError, OSError):
                judged = shown
        finally:
            self._finish_verdict()
        self.settle(judged, landed=True)

    def overdue(self) -> bool:
        """Срок финала прошёл, а заход ещё не отдал его."""
        return not self.done and time.monotonic() - self.started_at >= FINAL_BY

    def posters_left(self) -> float:
        """Секунды до потолка дозапроса обложек: он идёт от начала захода, а не от опроса."""
        return max(0.0, POSTERS_BY - (time.monotonic() - self.started_at))

    def settle(self, results: list[JsonValue], *, landed: bool = False) -> None:
        """Финал: к сроку - собранное, если ещё не отдан; досчитанный заход - всегда."""
        with self._lock:
            if self.done and not landed:
                return
            self.results = results
            # Time before the flag: a poll seeing ``done`` with zero time takes the job as stale.
            self.finished_at = time.monotonic()
            self.done = True

    def _capture(self, client: IndexerClient) -> None:
        self.client = client


__all__ = ["FINAL_BY", "POSTERS_BY", "SearchJob"]
