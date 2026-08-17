"""Совместимый фасад справки о картинах: прежние имена и проводка её сценариев.

Правила разбора статьи живут в :mod:`torrcast.domain.facts`, сеть и файлы - в
:mod:`torrcast.adapters.wiki`, а собирает их :class:`~torrcast.runtime.facts_wiring.
FactsWiring`. Отсюда берут справку прежние потребители: меню франшизы, гейт добора и
диагностические сценарии.
"""

from __future__ import annotations

# Статический список нужен mypy для реэкспортов.
__all__ = [
    "BLURB_CAP",
    "CACHE_PATH",
    "EMPTY_TTL",
    "FACTS_BUDGET",
    "HTTP_TIMEOUT",
    "RATINGS_PATH",
    "RU_NAMES_PATH",
    "SOURCE_JOIN",
    "SOURCE_MAP",
    "SOURCE_WIKI",
    "SOURCE_WIKIDATA",
    "TOPUP_LIMIT",
    "USER_AGENT",
    "Fact",
    "Facts",
    "Origin",
    "akin",
    "confirms",
    "english_title",
    "get_json",
    "hms",
    "latin_title",
    "minutes_of",
    "namesake",
    "origin",
    "origin_either",
    "picture_year",
    "read_origin",
    "read_published",
    "read_sparql",
    "redirected_name",
    "same_name",
    "sentence",
    "shorten",
    "sourced",
    "titles_for",
    "with_source",
    "without_source",
]

from collections.abc import Iterable
from typing import Any

from torrcast.domain.facts.akin import akin
from torrcast.domain.facts.confirms import confirms
from torrcast.domain.facts.english_title import english_title
from torrcast.domain.facts.fact import Fact
from torrcast.domain.facts.hms import hms
from torrcast.domain.facts.latin_title import latin_title
from torrcast.domain.facts.minutes_of import minutes_of
from torrcast.domain.facts.namesake import namesake
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.picture_year import picture_year
from torrcast.domain.facts.read_origin import read_origin
from torrcast.domain.facts.read_published import read_published
from torrcast.domain.facts.read_sparql import read_sparql
from torrcast.domain.facts.redirected_name import redirected_name
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.facts.sentence import sentence
from torrcast.domain.facts.settings import (
    BLURB_CAP,
    CACHE_PATH,
    EMPTY_TTL,
    FACTS_BUDGET,
    HTTP_TIMEOUT,
    RATINGS_PATH,
    RU_NAMES_PATH,
    SOURCE_JOIN,
    SOURCE_MAP,
    SOURCE_WIKI,
    SOURCE_WIKIDATA,
    TOPUP_LIMIT,
    USER_AGENT,
)
from torrcast.domain.facts.shorten import shorten
from torrcast.domain.facts.sourced import sourced
from torrcast.domain.facts.titles_for import titles_for
from torrcast.domain.facts.with_source import with_source
from torrcast.domain.facts.without_source import without_source
from torrcast.runtime.facts_wiring import FactsWiring
from torrcast.usecases.facts import Facts as _MenuFacts

#: Проводка справки на весь процесс: один HTTPS-клиент со своей памятью адресов, один
#: кэш рядом с состоянием и разобранные однажды выгрузки IMDb.
FACTS = FactsWiring()


class Facts(_MenuFacts):
    """Справка к меню франшизы на действующих адаптерах; всё прочее - в сценарии."""

    def __init__(
        self, pictures: Iterable[tuple[str, int | None]], budget: float = FACTS_BUDGET
    ) -> None:
        super().__init__(pictures, budget, store=FACTS.cache, source=FACTS.blurbs)


def origin(title: str, series: bool | None = False, budget: float = FACTS_BUDGET) -> Origin:
    """Паспорт картины из справки; см. :meth:`torrcast.usecases.passport.Passport.of`."""
    return FACTS.passport.of(title, series, budget)


def origin_either(title: str, budget: float = FACTS_BUDGET) -> Origin:
    """Паспорт, когда тип картины неизвестен; см. :class:`PassportEither`."""
    return FACTS.passport.either.of(title, budget)


def _cached_origin(title: str, series: bool | None) -> Origin | None:
    """Что лежит в кэше паспортов; ``None`` - про эту картину не спрашивали."""
    return FACTS.cache.read(title, series)


def get_json(
    host: str, path: str, params: dict[str, str], headers: dict[str, str], timeout: float
) -> Any:
    """GET с разбором JSON тем же клиентом, которым ходит справка."""
    return FACTS.client.get(host, path, params, headers, timeout)
