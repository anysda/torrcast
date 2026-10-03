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
