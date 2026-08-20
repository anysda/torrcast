"""Происхождение картины: отечественная опознаётся по паспорту, а не по догадке."""

from __future__ import annotations

from torrcast.domain.facts.origin import Origin
from torrcast.domain.kind import Kind
from torrcast.domain.picture import Picture
from torrcast.runtime.facts_wiring import FACTS
from torrcast.runtime.native_picture import native_picture


def _picture(title: str = "Брат", year: int | None = 1997, kind: Kind = "movie") -> Picture:
    return Picture(title=title, year=year, kind=kind)


def test_an_empty_original_with_a_known_russian_name_means_a_native_picture() -> None:
    """Оригинала нет, а русское имя справка знает - картина отечественная."""
    picture = _picture()

    native_picture(picture, "брат", Origin(name="Брат", year=1997, native=True))

    assert picture.native


def test_a_foreign_picture_stays_foreign() -> None:
    """Есть оригинальное название - картина не наша, и звук отбирается как прежде."""
    picture = _picture("Тачки")

    native_picture(picture, "тачки", Origin(title="Cars", name="Тачки", year=2006))

    assert not picture.native


def test_another_name_in_the_passport_proves_nothing() -> None:
    """Паспорт не про эту картину - молчим: одноимённость доказывается сверкой имён."""
    picture = _picture("Брат")

    native_picture(picture, "брат", Origin(name="Сестра", native=True))

    assert not picture.native


def test_the_passport_is_taken_from_the_cache_when_nobody_handed_it() -> None:
    """Паспорта на руках нет - читается уже сохранённый ответ, а не спрашивается сеть."""
    FACTS.cache.write("брат", False, Origin(name="Брат", year=1997, native=True))
    picture = _picture()

    native_picture(picture, "брат")

    assert picture.native


def test_a_series_asks_its_own_row_and_then_the_common_one() -> None:
    """У сериала свой ряд ключей; молчит он - берётся ответ «тип неизвестен»."""
    FACTS.cache.write("брат", None, Origin(name="Брат", native=True))
    series = _picture(kind="tv")

    native_picture(series, "брат")

    assert series.native


def test_a_silent_cache_leaves_everything_as_it_was() -> None:
    """Справка молчит или не успела - поведение прежнее, а не догадка о языке."""
    picture = _picture()

    native_picture(picture, "неизвестное кино")

    assert not picture.native
