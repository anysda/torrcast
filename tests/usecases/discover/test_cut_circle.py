"""Урезанный круг едет самим списком планов: показать можно, помнить как полный нельзя."""

from __future__ import annotations

import pytest

from tests.usecases.discover.world import Indexer, Said, row, wire_catalogue
from torrcast.domain.args import Args
from torrcast.domain.config import Config
from torrcast.domain.facts.origin import Origin
from torrcast.usecases.discover.cut_circle import CutCircle
from torrcast.usecases.discover.search_circle import search_circle

_CARS = [row("Тачки / Cars (2006) BDRip 1080p | D", "a", size_gb=5.0, seeders=66)]


@pytest.mark.parametrize(("cut", "marked"), [(("JacRed",), True), ((), False)])
def test_a_circle_whose_waited_source_gave_up_comes_back_marked(
    cut: tuple[str, ...], marked: bool
) -> None:
    wire_catalogue()
    client = Indexer(answers={"тачки": _CARS})
    client.cut = cut  # type: ignore[attr-defined]

    plans = search_circle(
        Config(prowlarr_apikey="KEY"),
        Args(query=["тачки"]),
        Said(),
        indexer=lambda *_a, **_k: client,
        passport=lambda *_a, **_k: Origin(),
    )

    assert [plan.picture.title for plan in plans] == ["Тачки"]
    assert isinstance(plans, CutCircle) is marked
