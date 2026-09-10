"""Проверяет shelf_tiles: плитка полки несёт ровно поля контракта ``/api/shelves``."""

from torrcast.domain.facts.origin import Origin
from torrcast.domain.json_value import JsonValue
from torrcast.domain.picture import Picture
from web.shelf_tiles import shelf_tiles


def _with_poster(records: list[JsonValue]) -> list[JsonValue]:
    """``offer``-подделка: дописывает обложку каждой записи-плитке."""
    return [{**r, "poster": "abc"} if isinstance(r, dict) else r for r in records]


def test_a_picture_becomes_a_tile_with_the_contract_fields_only() -> None:
    """Розыскное ``original`` снаружи не видно, обложку дописывает ``offer``."""
    tiles = shelf_tiles(
        [Picture(title="Матрица", year=1999)],
        offer=_with_poster,
        passport=lambda title, series, timeout: Origin(),
    )

    assert len(tiles) == 1
    tile = tiles[0]
    assert isinstance(tile, dict)
    assert set(tile) == {"key", "title", "shown", "year", "kind", "quality", "poster", "query"}
    assert tile["title"] == "Матрица"
    assert tile["poster"] == "abc"
