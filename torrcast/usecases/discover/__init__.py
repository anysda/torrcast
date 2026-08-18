"""Часть CLI; публичный фасад - :mod:`torrcast.cli`.

Реэкспорт круга поиска: запрос к индексерам, второй заход по строке и по второму имени,
строки отказов и планы меню. Ни строчки логики - каждая единица живёт в своём файле.
"""

from __future__ import annotations

from dataclasses import replace

from torrcast.domain.config import Config
from torrcast.domain.episode import Episode
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.same_name import same_name
from torrcast.domain.facts.settings import FACTS_BUDGET
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL, SECOND_LEAST
from torrcast.domain.infra_error import InfraError
from torrcast.domain.menu_order import menu_order
from torrcast.domain.not_found_error import NotFoundError
from torrcast.domain.other_words import other_words
from torrcast.domain.picture import Picture
from torrcast.domain.profile import CAUTIOUS, Profile
from torrcast.domain.release import Release
from torrcast.domain.slugify import slugify
from torrcast.domain.split_franchise_index import split_franchise_index
from torrcast.domain.transliterate import transliterate
from torrcast.ports.progress import Progress
from torrcast.usecases.discover._ask import _ask
from torrcast.usecases.discover._asked_kind import _asked_kind
from torrcast.usecases.discover._no_budget import _no_budget
from torrcast.usecases.discover._nothing import _nothing
from torrcast.usecases.discover._query_note import _query_note
from torrcast.usecases.discover._reread import (
    _relayout,
    _season_asked,
    _season_reread,
    _titled_number,
)
from torrcast.usecases.discover._search import _search
from torrcast.usecases.discover._search_state import _configure_discover
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover._vouched import _vouched
from torrcast.usecases.discover.discover import Discover
from torrcast.usecases.discover.kin_line import KIN_SHOWN, _kin, kin_line
from torrcast.usecases.discover.season_gaps import season_gaps
from torrcast.usecases.discover.silent_swarm import silent_swarm
from torrcast.usecases.discover.unfit_line import unfit_line
from torrcast.usecases.discover.unfit_pool import unfit_pool
from torrcast.usecases.discover.worth_asking_original import worth_asking_original

__all__ = [
    "CAUTIOUS",
    "CIRCLE_SHARE",
    "FACTS_BUDGET",
    "GOAL",
    "KIN_SHOWN",
    "SECOND_LEAST",
    "Config",
    "Discover",
    "Episode",
    "InfraError",
    "NotFoundError",
    "Origin",
    "Picture",
    "Profile",
    "Progress",
    "Release",
    "_ask",
    "_asked_kind",
    "_configure_discover",
    "_kin",
    "_no_budget",
    "_nothing",
    "_query_note",
    "_relayout",
    "_search",
    "_season_asked",
    "_season_reread",
    "_second_language",
    "_titled_number",
    "_vouched",
    "kin_line",
    "menu_order",
    "other_words",
    "replace",
    "same_name",
    "season_gaps",
    "silent_swarm",
    "slugify",
    "split_franchise_index",
    "transliterate",
    "unfit_line",
    "unfit_pool",
    "worth_asking_original",
]
