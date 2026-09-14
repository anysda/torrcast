"""Зеркало сведения: раздачи садятся в плитки каталога, пустые гаснут после круга."""

from __future__ import annotations

from typing import Any

from hass.catalog_merge import catalog_merge
from torrcast.domain.json_value import JsonValue

_Record = dict[str, JsonValue]

_TILE: _Record = {"key": "movie:матрица:1999", "title": "Матрица", "year": 1999, "kind": "movie",
                  "original": "The Matrix"}  # fmt: skip
_OTHER: _Record = {"key": "movie:матрица-перезагрузка:2003", "title": "Матрица: Перезагрузка",
                   "year": 2003, "kind": "movie", "original": "The Matrix Reloaded"}  # fmt: skip
_HIT: _Record = {"key": "movie:the-matrix:1999", "title": "The Matrix", "year": 1999,
                 "kind": "movie", "original": "", "pick": 1}  # fmt: skip
_STRAY: _Record = {"key": "movie:matrix-x:2020", "title": "Matrix X", "year": 2020,
                   "kind": "movie", "original": "", "pick": 2}  # fmt: skip


def _shape(records: list[Any]) -> list[tuple[str, Any, Any, Any]]:
    return [(r["key"], r.get("slot"), r.get("pending"), r.get("dim")) for r in records]


def test_while_the_circle_runs_a_hit_lands_in_its_tile_and_the_rest_wait() -> None:
    merged = catalog_merge([_TILE, _OTHER], [_STRAY, _HIT], done=False)
    assert _shape(merged) == [
        ("movie:the-matrix:1999", "movie:матрица:1999", None, None),
        ("movie:матрица-перезагрузка:2003", None, True, None),
        ("movie:matrix-x:2020", None, None, None),
    ]


def test_after_the_whole_circle_the_circle_order_stands_and_empty_tiles_dim() -> None:
    merged = catalog_merge([_TILE, _OTHER], [_STRAY, _HIT], done=True)
    assert _shape(merged) == [
        ("movie:matrix-x:2020", None, None, None),
        ("movie:the-matrix:1999", "movie:матрица:1999", None, None),
        ("movie:матрица-перезагрузка:2003", None, None, True),
    ]


def test_a_namesake_of_another_year_and_kind_is_not_the_same_picture() -> None:
    series: _Record = {**_HIT, "year": 2001, "kind": "tv"}
    merged = catalog_merge([_TILE], [series], done=True)
    assert _shape(merged) == [
        ("movie:the-matrix:1999", None, None, None),
        ("movie:матрица:1999", None, None, True),
    ]
