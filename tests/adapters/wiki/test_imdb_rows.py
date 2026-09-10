"""Правила одной строки подсказчика IMDb: год, род, картинка, имя, ужатый адрес."""

from __future__ import annotations

from typing import Any

from torrcast.adapters.wiki.imdb_rows import (
    _fits,
    _image,
    _otherwise_named,
    _same_name,
    _sized,
)
from torrcast.adapters.wiki.poster_files import POSTER_WIDTH
from torrcast.domain.facts.ask import Ask

RAW = "https://m.media-amazon.com/images/M/MV5BNWI5OTEzMzE@._V1_.jpg"


def _row(
    one: str = "tt0079077", name: str = "Mimi", year: int | None = 1979, kind: str = "movie"
) -> dict[str, Any]:
    return {"id": one, "l": name, "y": year, "qid": kind, "i": {"imageUrl": RAW}}


def test_fits_checks_id_picture_kind_and_the_exact_year() -> None:
    ask = Ask("Un dramma borghese", 1979, "movie")

    assert _fits(ask, _row())
    assert not _fits(ask, _row(year=1980)), "соседний год - соседняя картина"
    assert not _fits(ask, _row(kind="videoGame")), "игра - не картина"
    assert not _fits(ask, _row(one="nm0079077")), "персона - не картина"
    assert not _fits(ask, {**_row(), "i": None}), "строка без картинки - пустота"


def test_image_reads_the_picture_address_only() -> None:
    assert _image(_row()) == RAW
    assert _image(None) == ""
    assert _image({"l": "Mimi"}) == ""


def test_sized_offers_the_narrowed_address_first() -> None:
    assert _sized(RAW) == [
        f"https://m.media-amazon.com/images/M/MV5BNWI5OTEzMzE@._V1_UX{POSTER_WIDTH}_.jpg",
        RAW,
    ]


def test_same_name_compares_slugs_not_letters() -> None:
    assert _same_name("Mimi", _row(name="Mimi"))
    assert _same_name("mimi ", _row(name=" Mimi"))
    assert not _same_name("Un dramma borghese", _row())


def test_otherwise_named_takes_only_full_names_without_nesting() -> None:
    rows = [_row(name="Mimi")]

    assert _otherwise_named("Un dramma borghese", rows) == rows
    assert _otherwise_named("Brat", rows) == [], "однословному запросу тёзка не верится"
    assert _otherwise_named("The Paradise", rows) == rows
    assert _otherwise_named("The Paradise", [_row(name="The Paradise Hills")]) == []
