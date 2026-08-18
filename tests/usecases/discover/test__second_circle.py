"""Зеркало круга добора: чем именно спрошен каталог и с каким полом бюджета."""

from __future__ import annotations

from tests.usecases.discover.world import Indexer, Said, franchise, row, wire_catalogue
from torrcast.adapters.prowlarr.raw_result import RawResult
from torrcast.domain.facts.origin import Origin
from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL
from torrcast.domain.picture import Picture
from torrcast.usecases.discover._second_circle import _second_circle

_RU = [row("Психо / Psycho (1960) DVDRip", "a")]
_LATIN = [row("Psycho 1960 BDRip 1080p", "b")]
_ABOUT = Origin(title="Psycho")


def _circle(
    client: Indexer,
    name: str = "психо",
    alt: str = "Psycho",
    about: Origin = _ABOUT,
    found: list[Picture] | None = None,
    raw: list[RawResult] | None = None,
) -> list[RawResult]:
    wire_catalogue()
    return _second_circle(
        client,
        name,
        alt,
        None,
        about,
        franchise("психо", _RU) if found is None else found,
        _RU if raw is None else raw,
        Said(),
    )


def test_the_circle_asks_the_name_of_the_top_up_and_merges_both_answers() -> None:
    """Выдачи склеиваются, а не заменяются: русские имена несут озвучки и оригинал."""
    client = Indexer(_LATIN)

    merged = _circle(client)

    assert client.asked == ["Psycho"]
    assert len(merged) == 2


def test_the_floor_of_the_circle_is_a_whole_goal_and_is_given_back() -> None:
    """🔴 TC-386. Медленный, но живой индексер в остаток цели не укладывается."""
    client = Indexer(_LATIN)

    _circle(client)

    assert client.floors == [GOAL], "круг добора спрошен с полом в целую цель"
    assert client.cap_floor == CIRCLE_SHARE, "после захода пол возвращён обычному"


def test_a_year_the_first_circle_never_saw_refines_the_russian_name() -> None:
    """Паспорт назвал год, которого в первом круге нет - уточняем исходное имя им.

    Это всё тот же один добор, но русская строка сохраняет релизы с озвучкой, ради
    которых человек и назвал картину по-русски.
    """
    rows = [
        row("Девять / Nine (2000) BDRip 1080p", "a"),
        row("Девять 2 / Nine 2 (2016) BDRip 1080p", "c"),
    ]
    client = Indexer(_LATIN)

    _circle(
        client,
        name="девять",
        alt="Nine",
        about=Origin(title="Nine", year=2009),
        found=franchise("девять", rows),
        raw=rows,
    )

    assert client.asked == ["девять 2009"]
