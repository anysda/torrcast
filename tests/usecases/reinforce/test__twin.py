"""Кого из приехавших после добора сверять с той картиной, за которой шли."""

from __future__ import annotations

from tests.usecases.reinforce.stand import releases, row
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.usecases.reinforce._twin import _twin


def _picture(title: str, year: int, rows: int) -> Picture:
    """Картина ровно с тем числом раздач, которым меряется вожак франшизы."""
    return Picture(
        title=title,
        year=year,
        releases=releases(
            [row(f"{title} / X ({year}) BDRip 1080p", chr(97 + n)) for n in range(rows)]
        ),
    )


def test_the_year_of_the_reference_beats_the_crowd() -> None:
    """🔴 На «cars» добор приносит франшизу, и вожаком в ней встают «Тачки 3».

    Сверять гейту надо картину ТОГО ЖЕ года, иначе 2017 против 2006 читается подменой,
    и выбрасывается ровно та выдача, за которой ходили.
    """
    ours, crowd = _picture("Тачки", 2006, 4), _picture("Тачки 3", 2017, 14)

    twin = _twin([crowd, ours], Origin(year=2006), before=ours)

    assert twin is ours, "самый раздаваемый - не тот, за кем шли"


def test_without_a_passport_year_the_one_we_followed_sets_it() -> None:
    """Справка промолчала - год берётся у той картины, за которой шли."""
    ours, crowd = _picture("Тачки", 2006, 4), _picture("Тачки 3", 2017, 14)

    assert _twin([crowd, ours], Origin(), before=ours) is ours


def test_nobody_of_the_right_year_hands_it_back_to_the_leader() -> None:
    """Картины нужного года среди приехавших нет - сверять идёт вожак."""
    crowd, other = _picture("Тачки 3", 2017, 14), _picture("Тачки 2", 2011, 4)

    assert _twin([crowd, other], Origin(year=2006), before=None) is crowd


def test_a_year_apart_is_still_the_same_picture() -> None:
    """Год проката против года производства: на ±1 гейт спотыкался бы о честный добор."""
    near, crowd = _picture("Тачки", 2007, 2), _picture("Тачки 3", 2017, 14)

    assert _twin([crowd, near], Origin(year=2006), before=None) is near
