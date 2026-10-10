"""The picture of the year the viewer named leads the menu over the franchise line."""

from __future__ import annotations

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.usecases.discover._search_state import _configure_recognize
from torrcast.usecases.discover.search_circle import search_circle

_POOL = [
    row("Призрак в доспехах / Kokaku kidotai (1995) BDRip 1080p", "a", indexer="JacRed"),
    row("Призрак в доспехах / Kokaku kidotai (1995) BDRip 720p", "b", indexer="JacRed"),
    row("Призрак в доспехах 2: Невинность / Innocence (2004) BDRip 1080p", "c", indexer="JacRed"),
    row(
        "Призрак в доспехах / Kokaku Kidotai (2026) WEB-DL 1080p [S01, 1-10 из 12]",
        "d",
        indexer="Knaben",
    ),
]


def test_the_year_named_leads_the_franchise_line() -> None:
    """«Призрак в доспехах 2026»: сериал первым, хотя линейка начинается с фильма 1995."""
    wire_catalogue()
    known = MapPicture("Призрак в доспехах", 2026, True, "Kôkaku Kidôtai", 2506)
    _configure_recognize(lambda _query, _wait: known)
    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["Призрак в доспехах 2026"]),
        Said(),
        indexer=lambda *_args: Indexer(rows=_POOL),
    )

    assert [(p.picture.year, p.picture.kind) for p in plans][:2] == [(2026, "tv"), (1995, "movie")]


_BRAT = [
    row("Брат (1997) WEB-DL 1080p", "e"),
    row("Брат / Brother (Алексей Балабанов) [1997, Россия, драма, WEB-DLRip-AVC]", "f"),
    row("Брат Кадфаэль 3 сезон (1-3 из 3) / Cadfael (1997) DVDRip | AVC", "g"),
    row("Брат Кадфаэль / Cadfael / Сезон: 3 / Серии: 1-3(3) [1997, DVDRip]", "h"),
]


def test_a_recognized_film_of_the_year_sends_no_circle_for_a_season_of_its_neighbour() -> None:
    """«Брат 1997»: карта узнала фильм, и «Брат Кадфаэль» того же года - сосед по слову.

    Сериал с одним третьим сезоном рядом с узнанным фильмом звал сезонный круг: лишний
    поход за «Cadfael S01» и строка про сезон, которого никто не спрашивал.
    """
    wire_catalogue()
    _configure_recognize(lambda _query, _wait: MapPicture("Брат", 1997, False, "Brat", 118767))
    indexer = Indexer(rows=_BRAT)
    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["Брат 1997"]),
        Said(),
        indexer=lambda *_args: indexer,
    )

    assert (plans[0].picture.title, plans[0].picture.year) == ("Брат", 1997)
    assert not [asked for asked in indexer.asked if "S01" in asked], indexer.asked
