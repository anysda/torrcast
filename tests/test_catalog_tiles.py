"""Зеркало плиток каталога: карта сразу, подсказки IMDb там, где карта промолчала."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any, cast

from hass.catalog_index import CatalogIndex
from hass.catalog_tiles import CatalogTiles
from torrcast.domain.facts.imdb_rows import _RuName

_MATRIX: _RuName = ("tt0133093", "movie", "The Matrix", "1999", "Матрица")
_VOTES = {"tt0133093": 2_275_526, "tt0816692": 2_300_000, "tt3601194": 12}


def _index(*rows: _RuName) -> CatalogIndex:
    index = CatalogIndex(lambda: {row[4].lower(): [row] for row in rows}, lambda: _VOTES)
    index.warm()
    return index


def _now(job: Callable[[], None]) -> None:
    job()


def _suggest(rows: list[dict[str, Any]]) -> Callable[[str], list[dict[str, Any]]]:
    return lambda _query: rows


def test_the_map_answers_at_once_with_a_tile_of_the_same_shape_as_a_hit() -> None:
    tiles: list[Any] = CatalogTiles("матрица", _index(_MATRIX), _suggest([])).tiles()
    assert tiles == [
        {
            "pick": 0,
            "key": "movie:матрица:1999",
            "title": "Матрица",
            "shown": tiles[0]["shown"],
            "named": tiles[0]["named"],
            "year": 1999,
            "kind": "movie",
            "original": "The Matrix",
            "default": False,
        }
    ]


def test_suggestions_fill_in_where_the_map_is_silent_and_skip_the_obscure() -> None:
    rows = [
        {"id": "tt0816692", "l": "Interstellar", "y": 2014, "qid": "movie"},
        {"id": "tt3601194", "l": "Interstelar", "y": 2014, "qid": "movie"},
        {"id": "tt0133093", "l": "The Matrix", "y": 1999, "qid": "movie"},
        {"id": "tt0000001", "l": "A short", "y": 1999, "qid": "short"},
    ]
    tiles = CatalogTiles("интерстелар", _index(_MATRIX), _suggest(rows)).start(_now)
    shown = [(tile["title"], tile["original"]) for tile in cast("list[Any]", tiles.tiles())]
    # Имя по-русски берётся у карты по id: подсказчик зовёт картину латиницей.
    assert shown == [("Interstellar", ""), ("Матрица", "The Matrix")]


def test_a_silent_suggester_leaves_no_tiles_and_no_error() -> None:
    def broken(_query: str) -> list[dict[str, Any]]:
        raise OSError("обрыв")

    assert CatalogTiles("интерстелар", _index(), broken).start(_now).tiles() == []
