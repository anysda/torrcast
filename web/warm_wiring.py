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
from torrcast.runtime.menu_facts import MenuFacts
from torrcast.usecases.discover.search_circle import search_circle
from web.warm_cache import WarmCache

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


#: Один прогрев на процесс: его греет ``POST /api/seen``, из него берёт круг карточка.
WARM: Final = WarmCache(circle=_search, blurbs=_blurbs, spawn=_daemon)

__all__ = ["WARM"]
