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


def _mixed(count: int) -> list[Picture]:
    """count картин, где каждая вторая записана латиницей: Latin 0, Картина 1, ..."""
    return [
        Picture(title=f"Картина {index}" if index % 2 else f"Latin {index}", year=2001)
        for index in range(count)
    ]


def test_under_russian_a_shelf_drops_latin_tiles_and_tops_their_place_up(
    _russian_product: None,
) -> None:
    """Плитка без кириллицы на полку не идёт, а её место добирает следующая картина."""
    tiles = shelf_tiles(
        _mixed(8),
        offer=_with_poster,
        passport=lambda title, series, timeout: Origin(),
        limit=3,
    )

    assert [t["title"] for t in tiles if isinstance(t, dict)] == [
        "Картина 1",
        "Картина 3",
        "Картина 5",
    ]


def test_under_russian_a_latin_tile_never_reaches_the_poster_offer(
    _russian_product: None,
) -> None:
    """Отбор языка стоит ДО добора обложек: выброшенная плитка их не занимает."""
    asked: list[str] = []

    def _offer(records: list[JsonValue]) -> list[JsonValue]:
        asked.extend(str(r["title"]) for r in records if isinstance(r, dict))
        return _with_poster(records)

    shelf_tiles(_mixed(4), offer=_offer, passport=lambda t, s, to: Origin(), limit=2)

    assert asked == ["Картина 1", "Картина 3"], f"до обложек дошли выброшенные: {asked}"


def test_an_unplayable_tile_is_dropped_and_its_place_is_topped_up() -> None:
    """Плитка, которую отбор не смог запустить, на полку не идёт - место добирает следующая."""

    def _playable(_query: str, key: str) -> bool:
        return "-1:" not in key and "-3:" not in key

    tiles = shelf_tiles(
        _pictures(6),
        offer=_with_poster,
        passport=lambda title, series, timeout: Origin(),
        playable=_playable,
        limit=4,
    )

    titles = [t["title"] for t in tiles if isinstance(t, dict)]
    assert "Картина 1" not in titles and "Картина 3" not in titles
    assert len(titles) == 4


def test_an_unknown_verdict_tile_stays_on_the_shelf() -> None:
    """«Не знаю» (сеть легла, TorrServer не ответил) не выбрасывает картину - она остаётся,
    ровно как при честном «играет» (:data:`web.shelf_playable.Verdict`)."""

    def _unknown(_query: str, key: str) -> bool | None:
        return None if "-1:" in key or "-3:" in key else True

    tiles = shelf_tiles(
        _pictures(6),
        offer=_with_poster,
        passport=lambda title, series, timeout: Origin(),
        playable=_unknown,
        limit=6,
    )

    titles = [t["title"] for t in tiles if isinstance(t, dict)]
    assert "Картина 1" in titles and "Картина 3" in titles
    assert len(titles) == 6


def test_a_tile_without_a_poster_never_asks_whether_it_plays() -> None:
    """Играбельность дорогая - отбор без обложки её вовсе не спрашивает."""
    asked: list[str] = []

    def _playable(query: str, _key: str) -> bool:
        asked.append(query)
        return True

    shelf_tiles(_pictures(4), offer=_odd_posters, passport=lambda t, s, to: Origin(), limit=2)
    shelf_tiles(
        _pictures(4),
        offer=_odd_posters,
        passport=lambda t, s, to: Origin(),
        playable=_playable,
        limit=2,
    )

    assert asked == ["Картина 1", "Картина 3"], f"плитку без обложки отбор всё же спросил: {asked}"


def test_under_english_a_latin_tile_stays_on_the_shelf(_english: None) -> None:
    """Английская сторона не сдвигается ни на плитку: латиница там и есть имя показа."""
    tiles = shelf_tiles(
        _mixed(4),
        offer=_with_poster,
        passport=lambda title, series, timeout: Origin(),
        limit=4,
    )

    assert [t["title"] for t in tiles if isinstance(t, dict)] == [
        "Latin 0",
        "Картина 1",
        "Latin 2",
        "Картина 3",
    ]
