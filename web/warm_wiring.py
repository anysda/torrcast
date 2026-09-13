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
from web.preview import _facts
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
    """Завести родню плитки после её круга, не задерживая прогрев."""
    RELATED.of(picture[0], len(picture) == 3 and picture[2] == "tv")


def _background_kin(picture: FactPicture) -> None:
    """Finish one visible franchise in its own lane before taking the next tile."""
    RELATED.finish([picture])


def _prime(pictures: list[FactPicture]) -> None:
    """Start the hovered tile's facts shared with the card that opens it."""
    for picture in pictures:
        title, year = picture[:2]
        kind = picture[2] if len(picture) == 3 else "movie"
        if year is not None:
            _facts.of(title, year, kind)


#: Заказ плиток полки: круг идёт через него, чтобы родня была своей картины.
TARGETS: Final = WarmTargets(
    circle=_search, prime=_prime, kin=_kin, background_kin=_background_kin, spawn=_daemon
)
#: Один прогрев на процесс: его греет ``POST /api/seen``, из него берёт круг карточка.
WARM: Final = WarmCache(circle=TARGETS.search, blurbs=_blurbs, spawn=_daemon)
TARGETS.ask = WARM.ask
#: Общая карточке и прогреву родня: первый клик читает уже идущий или готовый кэш.
RELATED: Final = RelatedLookup(
    franchise=FACTS.franchise.of,
    passport=FACTS.passport.of,
)

__all__ = ["RELATED", "TARGETS", "WARM"]
