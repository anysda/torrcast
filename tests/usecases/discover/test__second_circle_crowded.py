"""Тесное имя, которое отстояла карта: второй круг спрашивает его с годом, а не латиницей."""

from __future__ import annotations

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.facts.origin import Origin
from torrcast.domain.picture import Picture
from torrcast.usecases.discover._second_circle import _second_circle

_UP = [row("Вверх / Up (2009) BDRip 1080p", "a")]


def _asked(crowded: bool) -> list[str]:
    wire_catalogue()
    client = Indexer([row("Up 2009 BDRip 1080p", "b")])
    found = [Picture(title="Вверх", year=2009, original="Up")]
    about = Origin(title="Up", year=2009)

    _second_circle(client, "вверх", "Up", None, about, found, _UP, Said(), crowded)

    return client.asked


def test_a_crowded_name_is_asked_with_its_year() -> None:
    """🔴 «Up» на «Вверх» привозил 118 картин против 45, и гейт отвергал весь круг."""
    assert _asked(crowded=True) == ["вверх 2009"]


def test_a_name_the_map_did_not_have_to_defend_is_asked_by_its_original() -> None:
    """Год в первом круге уже есть и имя не тесное - круг прежний, латиницей («Психо»)."""
    assert _asked(crowded=False) == ["Up"]
