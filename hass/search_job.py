"""Один фоновый заход прогрессивного поиска: круг, память показанного и приговор обложек.

Круг идёт через общий кэш кругов (:class:`web.warm_cache.WarmCache`), если он назван: тогда
поиск, прогрев выдачи, карточка и «похожие» платят за запрос ОДИН круг. Раньше выдача
считала свой круг мимо кэша, и первая же плитка той же выдачи гнала его второй раз.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from hass import searching
from hass.search_results import _hit
from hass.searching import Detect, Offer, Remember
from torrcast.cli.parse_args import parse_args
from torrcast.domain.config import Config
from torrcast.domain.json_value import JsonValue
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

#: Тот же тип, что :data:`hass.search_progress.ProgressiveSearch`; назван тут, чтобы не
#: замыкать импорт по кругу.
_Search = Callable[
    [Config, "Args", Progress, Profile, Callable[[IndexerClient], None]], "list[Plan]"
]


class _Shared(Protocol):
    """Общий кэш кругов: один круг на запрос для всех, кто его спросил."""

    def take(self, query: str, circle: Callable[[str], list[Plan]] | None = None) -> list[Plan]: ...


@dataclass
class SearchJob:
    """Один фоновый поиск: клиент индексеров, как только он появился, и итог."""

    client: IndexerClient | None = None
    done: bool = False
    error: str | None = None
    results: list[JsonValue] = field(default_factory=list)
    finished_at: float = 0.0

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
        except TorrcastError as refusal:
            self.error = str(refusal)
            self._finish()
            return
        remember(args.title_query, [(plan.picture.key, _named(plan.picture)) for plan in plans])
        taken = enter_take(plans, args.title_query).number
        hits = [_hit(plan.picture, n, default=n == taken) for n, plan in enumerate(plans, start=1)]
        # Имя обложки даёт тот же приговор, что и обычному поиску (:data:`hass.searching.OFFER`):
        # без этого шага веб-выдача шла совсем без обложек. Отказ приговора выдачу не роняет.
        try:
            self.results = (searching.OFFER if offer is None else offer)(hits)
        except (TorrcastError, OSError):
            self.results = hits
        self._finish()

    def _capture(self, client: IndexerClient) -> None:
        self.client = client

    def _finish(self) -> None:
        self.done = True
        self.finished_at = time.monotonic()


__all__ = ["SearchJob"]
