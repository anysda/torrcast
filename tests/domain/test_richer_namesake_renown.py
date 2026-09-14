"""Тощий тёзка, которого карта IMDb доказывает: :func:`_richer_namesake` с ``imdb``."""

from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.picture import Picture
from torrcast.domain.release import Release
from torrcast.domain.richer_namesake import _richer_namesake
from torrcast.domain.slugify import slugify


def _picture(title: str, year: int, copies: int, kind: str = "movie") -> Picture:
    releases = [Release(raw_name=title, title=title) for _ in range(copies)]
    return Picture(title=title, year=year, kind=kind, releases=releases)  # type: ignore[arg-type]


def _known(rows: list[MapPicture]):  # type: ignore[no-untyped-def]
    return lambda title: [row for row in rows if slugify(row.name) == slugify(title)]


_US = MapPicture("Мы", 2019, False, "Us", 399488)
_SHADOWS = MapPicture("Чем мы заняты в тени", 2019, True, "What We Do in the Shadows", 129020)
_GROUPS = {
    "мы": [_picture("Мы", 2019, 2)],
    "чем-мы-заняты-в-тени": [
        _picture("Чем мы заняты в тени", 2019, 2, "tv"),
        _picture("Чем мы заняты в тени", 2020, 2, "tv"),
    ],
}


def test_a_proven_picture_keeps_its_name_against_a_richer_but_less_known_neighbour() -> None:
    """🔴 «Мы» (Us, 399 488 голосов) против «Чем мы заняты в тени» (129 020)."""
    assert _richer_namesake(_GROUPS, "мы", imdb=_known([_US, _SHADOWS])) is None


def test_a_better_known_neighbour_still_takes_the_name() -> None:
    """Голосов у соседа больше - счёт выдачи и карта согласны, имя уходит ему."""
    louder = MapPicture("Чем мы заняты в тени", 2019, True, "Shadows", 500000)

    assert _richer_namesake(_GROUPS, "мы", imdb=_known([_US, louder])) == "чем-мы-заняты-в-тени"


def test_a_namesake_the_map_does_not_know_yields_as_before() -> None:
    """«Властелина» (1999) карта не знает: он уступает «Властелину колец», как уступал."""
    groups = {
        "властелин": [_picture("Властелин", 1999, 1)],
        "властелин-колец": [_picture("Властелин колец", 2001 + n, 20) for n in range(3)],
    }
    lord = MapPicture("Властелин колец", 2001, False, "The Lord of the Rings", 2000000)

    assert _richer_namesake(groups, "властелин", imdb=_known([lord])) == "властелин-колец"


def test_a_third_name_is_not_proven_by_the_map() -> None:
    """Псевдоним из выдачи картину запроса не называет: ``incumbent`` карта не спасает."""
    groups = {
        "часовые": [_picture("Часовые", 2023, 1)],
        "стражи-галактики": [_picture("Стражи Галактики", 2014 + n, 30) for n in range(5)],
    }
    guards = MapPicture("Часовые", 2023, False, "Sentinelles", 900000)

    found = _richer_namesake(groups, "стражи", incumbent="часовые", imdb=_known([guards]))

    assert found == "стражи-галактики"
