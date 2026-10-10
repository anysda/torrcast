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
from torrcast.domain.reason_of import reason_of
from torrcast.domain.search_refusal_reason import SearchRefusalReason
from torrcast.domain.torrcast_error import TorrcastError
from torrcast.domain.tune import tune
from torrcast.ports.progress.progress import Progress
from torrcast.ports.progress.slot import progress
from torrcast.ports.torrent_catalogue.indexer_client import IndexerClient
from torrcast.usecases.choice._named import _named
from torrcast.usecases.choice.enter_take import enter_take
from web.warm_seat import WarmSeat

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
#: How long the page may keep listening for the refusal of a circle that outran the deadline.
REFUSAL_BY: Final = 45.0
#: The honest end of a search that could not ask the whole catalogue or took too long.
FAILED: Final = SearchRefusalReason("web.search.failed", {})

#: Тот же тип, что :data:`hass.search_progress.ProgressiveSearch`; назван тут, чтобы не
#: замыкать импорт по кругу.
_Search = Callable[
    [Config, "Args", Progress, Profile, Callable[[IndexerClient], None]], "list[Plan]"
]


class _Shared(Protocol):
    """Общий кэш кругов: один круг на запрос для всех, кто его спросил."""

    def take(
        self, query: str, circle: Callable[[str], list[Plan]] | None = None, retry: bool = False
    ) -> list[Plan]: ...


@dataclass
class SearchJob(SearchPosterVerdict):
    """Один фоновый поиск: клиент индексеров, как только он появился, и итог."""

    client: IndexerClient | None = None
    done: bool = False
    error: SearchRefusalReason | None = None
    results: list[JsonValue] = field(default_factory=list)
    finished_at: float = 0.0
    #: The deadline published a usable snapshot while the circle still owns the job.
    timed_out: bool = False
    posters: dict[str, JsonValue] = field(default_factory=dict)
    #: A poll has seen this job's covers coming: the job then stays until the poster cap.
    promised: bool = False
    #: The finished circle's list before its poster verdict: previews show it at once.
    hits: list[JsonValue] = field(default_factory=list)
    #: Картины каталога под этот запрос (:mod:`hass.catalog_tiles`); без них - только раздачи.
    catalog: CatalogTiles | None = None
    started_at: float = field(default_factory=time.monotonic)
    #: A poll has put this job's first row on screen: it is never held for covers again.
    drawn: bool = False
    #: Keys of pictures a poll has put on screen, and when a later row first offered each.
    on_screen: set[str] = field(default_factory=set)
    appeared: dict[str, float] = field(default_factory=dict)
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
            # A new job is someone asking: a cut refusal still remembered is no answer to it.
            with WarmSeat.watching(self._capture):  # a warmup circle taken over hands it too
                plans = circle(query) if warm is None else warm.take(query, circle, retry=True)
        except NothingFoundError as nothing:
            # Only a circle every indexer answered may say «nothing»: an empty cut circle has
            # not searched the catalogue, and the page says the search failed instead.
            plans, self.error = [], None if nothing.whole else FAILED
        except TorrcastError as refusal:
            # The page receives a key and values, not process words in the machine's language.
            plans, self.error = [], reason_of(refusal)
        if self.error is not None:
            # A catalogue tile is a useful preview while the circle runs, but it cannot turn a
            # completed named refusal into a seemingly successful search.  The page retains
            # any preview it has already drawn and puts this reason above it.
            self.settle([], landed=True)
            return
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
            self.timed_out = not landed

    def late(self, within: float) -> bool:
        """The deadline snapshot is out, its circle still runs, and ``within`` s have not passed."""
        with self._lock:
            running = self.done and self.timed_out and self.error is None
            return running and time.monotonic() - self.started_at < within

    def _capture(self, client: IndexerClient) -> None:
        self.client = client


__all__ = ["FAILED", "FINAL_BY", "POSTERS_BY", "REFUSAL_BY", "SearchJob"]
