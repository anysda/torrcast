"""Совместимый фасад поиска раздач.

Сам поиск разложен по слоям: правила круга и бюджетов - в ``torrcast/domain/``, клиент
Prowlarr и разбор его выдачи - в :mod:`torrcast.adapters.prowlarr`. Отсюда его берут
щупы и прежние импорты.
"""

from torrcast.adapters.prowlarr.from_json import from_json as from_json
from torrcast.adapters.prowlarr.from_torznab import from_torznab as from_torznab
from torrcast.adapters.prowlarr.magnet_for import PUBLIC_TRACKERS as PUBLIC_TRACKERS
from torrcast.adapters.prowlarr.magnet_for import magnet_for as magnet_for
from torrcast.adapters.prowlarr.merge import merge as merge
from torrcast.adapters.prowlarr.prowlarr import Prowlarr as Prowlarr
from torrcast.adapters.prowlarr.prowlarr_http_client import (
    _IndexersUnavailableError as _IndexersUnavailableError,
)
from torrcast.adapters.prowlarr.raw_result import RawResult as RawResult
from torrcast.adapters.prowlarr.to_releases import to_releases as to_releases
from torrcast.domain.anime_query import anime_query as anime_query
from torrcast.domain.goal_spare import CIRCLE_SHARE as CIRCLE_SHARE
from torrcast.domain.goal_spare import GOAL as GOAL
from torrcast.domain.goal_spare import SECOND_LEAST as SECOND_LEAST
from torrcast.domain.indexer_budget import indexer_budget as indexer_budget
from torrcast.domain.quorum_indexer import QUORUM_INDEXERS as QUORUM_INDEXERS
from torrcast.domain.quorum_indexer import quorum_indexer as quorum_indexer
from torrcast.domain.response_budget import response_budget as response_budget

__all__ = [
    "CIRCLE_SHARE",
    "GOAL",
    "PUBLIC_TRACKERS",
    "QUORUM_INDEXERS",
    "SECOND_LEAST",
    "Prowlarr",
    "RawResult",
    "_IndexersUnavailableError",
    "anime_query",
    "from_torznab",
    "magnet_for",
    "merge",
    "quorum_indexer",
    "to_releases",
]
