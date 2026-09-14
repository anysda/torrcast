"""Второй заход на имени, которое отстояла карта IMDb: круг с годом вместо тесной латиницы."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.usecases.discover.world import Indexer, Said, pictures, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover._second_language import _second_language
from torrcast.usecases.discover.franchise_pick import franchise_pick

_RU = [
    row("Вверх / Up (2009) DVDRip", "a", seeders=3),
    row("Руки вверх! (1981) DVDRip", "b"),
    row("Руки вверх! (1981) VHSRip", "c"),
    row("Руки вверх! (2024) WEB-DL 1080p", "d"),
    row("Руки вверх! (2024) WEB-DL 720p", "e"),
]


def test_the_top_up_of_a_crowded_name_asks_the_russian_name_with_the_year(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 «Вверх» (Up, 2009): «Up» привозил 118 картин против 45, гейт отвергал круг."""
    wire_catalogue()
    up = [MapPicture("Вверх", 2009, False, "Up", 1254598)]
    composition.use_known_pictures(monkeypatch, lambda title: up if title == "Вверх" else [])
    found = franchise_pick("вверх", pictures(_RU))
    client = Indexer(answers={"вверх 2009": [row("Вверх / Up (2009) BDRip 1080p", "f")]})

    _second_language(
        client,
        "вверх",
        Args(query=["вверх"]),
        _RU,
        found,
        Said(),
        passport=lambda *_a, **_k: Origin(title="Up", year=2009, name="Вверх"),
    )

    assert [p.title for p in found] == ["Вверх"]
    assert client.asked == ["вверх 2009"]
