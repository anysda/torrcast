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


def _pictures(count: int) -> list[Picture]:
    """count разных картин: плитку отличаем по имени."""
    return [Picture(title=f"Картина {index}", year=2001) for index in range(count)]


def _odd_posters(records: list[JsonValue]) -> list[JsonValue]:
    """``offer``-подделка: обложку получают только записи с нечётным номером в имени."""
    out: list[JsonValue] = []
    for record in records:
        assert isinstance(record, dict)
        number = int(str(record["title"]).rsplit(" ", 1)[1])
        out.append({**record, "poster": "abc"} if number % 2 else record)
    return out


def test_tiles_without_a_poster_are_dropped_and_their_place_is_topped_up() -> None:
    """Картина без обложки на полку не попадает; её место занимает следующая с обложкой."""
    tiles = shelf_tiles(
        _pictures(6),
        offer=_odd_posters,
        passport=lambda title, series, timeout: Origin(),
        limit=3,
    )

    assert [t["title"] for t in tiles if isinstance(t, dict)] == [
        "Картина 1",
        "Картина 3",
        "Картина 5",
    ]


def test_a_dropped_tile_is_never_projected() -> None:
    """Отбор стоит ДО проекции: выброшенная плитка не спрашивает ни имени, ни паспорта."""
    asked: list[str] = []

    def _passport(title: str, _series: bool, _timeout: float) -> Origin:
        asked.append(title)
        return Origin()

    tiles = shelf_tiles(_pictures(4), offer=_odd_posters, passport=_passport, limit=2)

    assert len(tiles) == 2
    assert asked == ["Картина 1", "Картина 3"], f"до проекции дошли выброшенные: {asked}"


def test_a_fully_silent_poster_source_leaves_the_shelf_untouched() -> None:
    """Граница отбора: имени нет НИ У КОГО - приговора не было, полка остаётся как собрана."""
    tiles = shelf_tiles(
        _pictures(5),
        offer=lambda records: records,
        passport=lambda title, series, timeout: Origin(),
        limit=3,
    )

    assert len(tiles) == 3
    assert all(isinstance(t, dict) and not t.get("poster") for t in tiles)
