"""Зеркало :mod:`hass.poster_of_the_year`: постер берётся только со сверенным годом."""

from __future__ import annotations

from hass.poster_of_the_year import poster_of_the_year

POSTER = b"\xff\xd8\xff\xe0poster"


def _poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
    return POSTER


def test_an_unconfirmed_year_leaves_the_picture_unfound() -> None:
    """🔴 Справка не подтвердила год - картинки нет, и в сеть за ней не ходят.

    Голое название ведёт в одну статью на всех тёзок: без этого «Паразиты» 1999, 2004 и
    2016 годов получили бы один постер на всех - постер «Паразитов» 2019-го.
    """
    asked: list[str] = []

    def poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        asked.append(name)
        return POSTER

    found = poster_of_the_year(
        "Паразиты", 2004, "movie", 1.0, poster, lambda title, year, kind, timeout: ""
    )

    assert found is None
    assert asked == []


def test_the_confirmed_name_is_the_one_asked_for() -> None:
    """Подтверждённое имя и есть то, под которым спрашивается постер."""
    asked: list[str] = []

    def poster(name: str, year: int | None, kind: str, timeout: float) -> bytes | None:
        asked.append(name)
        return POSTER

    found = poster_of_the_year(
        "Паразиты",
        2019,
        "movie",
        1.0,
        poster,
        lambda title, year, kind, timeout: f"{title} (фильм, {year})",
    )

    assert found == POSTER
    assert asked == ["Паразиты (фильм, 2019)"]


def test_a_picture_without_a_year_is_asked_for_as_it_is() -> None:
    """Года нет - сверять нечего и нечему противоречить: имя идёт как есть."""
    assert poster_of_the_year("Паразиты", None, "movie", 1.0, _poster, None) == POSTER


def test_a_reference_that_broke_off_gives_no_picture() -> None:
    """Справка оборвалась - картинки нет: несверенную брать нельзя даже при обрыве."""

    def correct(title: str, year: int, kind: str, timeout: float) -> str:
        raise TimeoutError("справка не ответила")

    assert poster_of_the_year("Паразиты", 2019, "movie", 1.0, _poster, correct) is None
