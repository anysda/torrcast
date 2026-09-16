"""Зеркало сведения: раздачи садятся в плитки каталога, пустые ждут и остаются живыми."""

from __future__ import annotations

from typing import Any

from hass.catalog_merge import catalog_merge
from torrcast.domain.json_value import JsonValue

_Record = dict[str, JsonValue]

#: Плитки каталога строятся тем же ``_hit``, что и находки, и несут ``pick`` нулём:
#: фикстура без него не поймала бы, что страница считает такую плитку находкой круга.
_TILE: _Record = {"key": "movie:матрица:1999", "title": "Матрица", "year": 1999, "kind": "movie",
                  "original": "The Matrix", "pick": 0}  # fmt: skip
_OTHER: _Record = {"key": "movie:матрица-перезагрузка:2003", "title": "Матрица: Перезагрузка",
                   "year": 2003, "kind": "movie", "original": "The Matrix Reloaded",
                   "pick": 0}  # fmt: skip
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


def test_after_the_whole_circle_no_tile_moves_and_an_empty_tile_stays_a_plain_tile() -> None:
    merged = catalog_merge([_TILE, _OTHER], [_STRAY, _HIT], done=True)
    assert _shape(merged) == [
        ("movie:the-matrix:1999", "movie:матрица:1999", None, None),
        ("movie:матрица-перезагрузка:2003", None, None, None),
        ("movie:matrix-x:2020", None, None, None),
    ], "курсор стоит на первой плитке: в конце круга под ним та же картина"


def test_the_circles_silence_about_a_picture_does_not_mark_the_tile() -> None:
    """Круг спрошен по набранному тексту, и его молчание - не приговор картине.

    Помеченную плитку страница гасила и отнимала у неё клик, а карточка той же картины,
    спрошенная по её собственному имени, приносила раздачи. Поэтому пометки нет вовсе:
    ни ``dim``, ни ``pending`` - после круга плитка каталога обычная и открывается.
    """
    series: _Record = {**_HIT, "year": 2001, "kind": "tv"}
    merged = catalog_merge([_TILE], [series], done=True)
    assert _shape(merged) == [
        ("movie:матрица:1999", None, None, None),
        ("movie:the-matrix:1999", None, None, None),
    ]
    marks = [set(record) & {"dim", "pending"} for record in merged if isinstance(record, dict)]
    assert marks == [set(), set()], "пометка вернулась: страница погасит плитку и отнимет клик"
    places = [record.get("pick", "нет") for record in merged if isinstance(record, dict)]
    assert places == ["нет", 1], (
        "плитка без находки назвалась находкой круга: карточка спросит раздачи набранным "
        "текстом, которым круг о ней и промолчал"
    )


def test_a_suggesters_guess_without_releases_leaves_after_the_circle() -> None:
    guess: _Record = {**_OTHER, "guess": True}
    assert _shape(catalog_merge([guess], [], done=False)) == [(_OTHER["key"], None, True, None)]
    assert catalog_merge([guess], [], done=True) == []
    assert "guess" not in catalog_merge([guess], [], done=False)[0]  # type: ignore[operator]
