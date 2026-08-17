"""Проверяет фасад поиска: он отдаёт те же самые единицы, что живут в слоях."""

from __future__ import annotations

from torrcast import search
from torrcast.adapters.prowlarr.from_json import from_json
from torrcast.adapters.prowlarr.from_torznab import from_torznab
from torrcast.adapters.prowlarr.magnet_for import PUBLIC_TRACKERS, magnet_for
from torrcast.adapters.prowlarr.merge import merge
from torrcast.adapters.prowlarr.prowlarr import Prowlarr
from torrcast.adapters.prowlarr.prowlarr_http_client import _IndexersUnavailableError
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.adapters.prowlarr.to_releases import to_releases
from torrcast.domain.anime_query import anime_query
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL, SECOND_LEAST
from torrcast.domain.indexer_budget import indexer_budget
from torrcast.domain.quorum_indexer import QUORUM_INDEXERS, quorum_indexer
from torrcast.domain.response_budget import response_budget


def test_фасад_отдаёт_те_же_единицы_а_не_их_копии() -> None:
    """Копия разъехалась бы с домом молча: подделка в тесте прошла бы мимо боевого кода."""
    assert search.Prowlarr is Prowlarr
    assert search.RawResult is RawResult
    assert search.merge is merge
    assert search.to_releases is to_releases
    assert search.magnet_for is magnet_for
    assert search.from_json is from_json
    assert search.from_torznab is from_torznab
    assert search.anime_query is anime_query
    assert search.quorum_indexer is quorum_indexer
    assert search.indexer_budget is indexer_budget
    assert search.response_budget is response_budget
    assert search._IndexersUnavailableError is _IndexersUnavailableError


def test_фасад_отдаёт_те_же_пороги() -> None:
    """Число, разъехавшееся с домом, - это второй порог, о котором никто не знает."""
    assert (search.GOAL, search.CIRCLE_SHARE, search.SECOND_LEAST) == (
        GOAL,
        CIRCLE_SHARE,
        SECOND_LEAST,
    )
    assert search.QUORUM_INDEXERS == QUORUM_INDEXERS
    assert search.PUBLIC_TRACKERS == PUBLIC_TRACKERS


def test_склейка_и_разбор_работают_через_фасад() -> None:
    """Прежние импорты остаются рабочими целиком, а не по именам."""
    rows = [
        search.RawResult("Матрица (1999) 1080p", "a" * 40, size=1, seeders=2, indexer="Knaben"),
        search.RawResult("Матрица 1999 1080p", "a" * 40, size=1, seeders=9, indexer="RuTor"),
    ]
    merged = search.merge(rows[:1], rows[1:])
    assert len(merged) == 1, "одна раздача от двух индексеров - одна строка"
    (release,) = search.to_releases(merged)
    assert release.title == "Матрица"
    assert release.seeders == 9
    assert release.magnet.startswith("magnet:?xt=urn:btih:")


def test_названо_ровно_то_что_обещано() -> None:
    """``__all__`` - обещание фасада; имя из него обязано существовать."""
    assert set(search.__all__) <= set(vars(search))
