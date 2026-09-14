"""Прогрев на действующих службах: один предмет на процесс.

Механика прогрева (:mod:`web.warm_cache`) ничего не знает ни про Prowlarr, ни про
Wikipedia: кому она ходит за кругом и за справкой, решается здесь и один раз - тем же
приёмом, каким собран добор справки (:mod:`torrcast.runtime.facts_wiring`).
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import TYPE_CHECKING, Final

from torrcast.adapters.chromecast.profile_detector import detector
from torrcast.adapters.filesystem.state.load_config import load_config
from torrcast.cli.parse_args import parse_args
from torrcast.domain.tune import tune
from torrcast.ports.progress.slot import progress
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.discover.search_circle import search_circle
from web.kin_ahead import KIN_AHEAD
from web.preview import _facts
from web.prime import prime
from web.related_lookup import RelatedLookup
from web.warm_cache import WarmCache
from web.warm_targets import WarmTargets

if TYPE_CHECKING:
    from torrcast.usecases.facts import FactPicture
    from torrcast.usecases.select.plan import Plan


def _daemon(job: Callable[[], None]) -> None:
    """Боевой фон: поток-демон, который никого не держит при выходе."""
    threading.Thread(target=job, daemon=True, name="warm-cache").start()


def _search(query: str) -> list[Plan]:
    """Боевой круг: ровно тот же, каким ищет и карточка, и строка поиска."""
    config = load_config()
    chosen = detector.detect(config)
    return search_circle(
        tune(config, chosen.profile), parse_args([query]), progress(), chosen.profile
    )


def _blurbs(pictures: list[FactPicture]) -> None:
    """Боевая справка: тот же добор, что и у карточки, но досиженный до кэша."""
    facts = MenuFacts(pictures)
    facts.start()
    facts.finish()


def _kin(picture: FactPicture) -> None:
    """Start a hovered shelf from the shared fact QID, not a second passport."""
    title, year = picture[:2]
    kind = picture[2] if len(picture) == 3 else "movie"
    if year is None:
        return
    # A hover is a warm-up, not an open card.  Marking it foreground let an
    # entire screen take precedence over the click it was meant to prepare.
    facts = _facts.of(title, year, kind, foreground=False)
    if kind == "movie" and (known := KIN_AHEAD.entity(title, year)):
        # A related tile carries the QID of its published shelf: no article step.
        RELATED.of(title, False, known)

    def start() -> None:
        entity = str(getattr(facts.ready(title, year), "entity", ""))
        if entity:
            RELATED.of(title, kind == "tv", entity)

    # A cache hit has no worker to notify us.  A cold fact calls back at the
    # first Wikipedia answer, before slower rating details and long-polling.
    start()
    facts.watch(start)


def _background_kin(picture: FactPicture) -> None:
    """Finish one visible franchise in its own lane before taking the next tile."""
    title, year = picture[:2]
    stored = FACTS.cache.blurbs([(title, year)]).get((title, year))
    if stored is not None and stored.missing and not stored.entity:
        # The card of a confirmed missing article shows no franchise: no passport for it.
        return
    RELATED.finish([picture])


def _prime(pictures: list[FactPicture]) -> None:
    """Start hovered facts and their shelf from the same proved identity."""
    for picture in pictures:
        _kin(picture)


def _prime_screen(pictures: list[FactPicture]) -> None:
    """Fill the persisted home screen in one source batch before its first visit."""

    def finish() -> None:
        # Two pictures make one extract packet.  Startup therefore keeps four of
        # Wikimedia's five lanes for a just-opened card; the former full screen wave
        # took all five and made a 700 ms related-tile click wait behind it.
        without_entity: list[FactPicture] = []
        for at in range(0, len(pictures), 2):
            for _ in range(2):
                facts = MenuFacts(pictures[at : at + 2])
                facts.start()
                facts.finish()
                facts._done.wait()
                for picture in pictures[at : at + 2]:
                    title, year = picture[:2]
                    kind = picture[2] if len(picture) == 3 else "movie"
                    ready = getattr(facts, "ready", None)
                    fact = ready(title, year) if ready else None
                    entity = str(getattr(fact, "entity", ""))
                    if entity:
                        RELATED.of(title, kind == "tv", entity)
                    elif not getattr(fact, "missing", False) and (
                        (title, year, kind) not in without_entity
                    ):
                        # A card with a confirmed missing article shows no franchise
                        # (web.preview._related_of); its passport only spent Wikipedia.
                        without_entity.append((title, year, kind))
        if without_entity:
            prime(RELATED, without_entity)

    _daemon(finish)


#: Заказ плиток полки: круг идёт через него, чтобы родня была своей картины.
TARGETS: Final = WarmTargets(
    circle=_search,
    prime=_prime,
    kin=_kin,
    prime_screen=_prime_screen,
    background_kin=_background_kin,
    spawn=_daemon,
)
#: Один прогрев на процесс: его греет ``POST /api/seen``, из него берёт круг карточка.
WARM: Final = WarmCache(circle=TARGETS.search, blurbs=_blurbs, spawn=_daemon)
TARGETS.ask = WARM.ask
#: Общая карточке и прогреву родня: первый клик читает уже идущий или готовый кэш.
RELATED: Final = RelatedLookup(
    franchise=FACTS.franchise.of,
    entity_kin=FACTS.franchise.by_entity,
    passport=FACTS.passport.of,
    warm=KIN_AHEAD.offer,
)
KIN_AHEAD.fetch = FACTS.franchise.by_entities

__all__ = ["RELATED", "TARGETS", "WARM"]
