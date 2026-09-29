"""Проверяет публикацию готовой полки и её заказ прогрева."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from torrcast.domain.json_value import JsonValue
from web.built_by_rule import FIELD, RULE
from web.drop_count import DropCount
from web.publish_shelf import publish_shelf
from web.warm_targets import WarmTarget

_MOMENT = datetime(2026, 9, 6, tzinfo=UTC)
_TILE: JsonValue = {
    "key": "movie:matrix:2026",
    "query": "Матрица",
    "title": "Матрица",
    "year": 2026,
    "kind": "movie",
}


def test_publish_orders_changed_tiles_before_storing_the_body(tmp_path: Path) -> None:
    """Первый заказ виден до записи тела; повтор тех же плиток заказа не получает."""
    current: dict[str, JsonValue] = {FIELD: RULE, "fresh": [], "popular": [], "built_at": None}
    ordered: list[list[WarmTarget]] = []
    stored: list[dict[str, JsonValue]] = []

    def warm(screen: list[WarmTarget], _later: list[WarmTarget]) -> None:
        assert stored == []
        ordered.append(screen)

    publish_shelf(
        current,
        current,
        "fresh",
        [_TILE],
        DropCount(),
        now=_MOMENT,
        limit=30,
        warm=warm,
        store=stored.append,
        path=tmp_path / "shelves.json",
        complete=False,
    )
    publish_shelf(
        stored[0],
        current,
        "fresh",
        [_TILE],
        DropCount(),
        now=_MOMENT,
        limit=30,
        warm=warm,
        store=stored.append,
        path=tmp_path / "shelves.json",
        complete=False,
    )

    assert len(ordered) == 1
    assert len(stored) == 2
