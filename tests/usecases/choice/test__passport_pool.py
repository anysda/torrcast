"""Паспорт дефолтной картины сверяется с ней самой и с картой IMDb, а не только со статьёй."""

from __future__ import annotations

import pytest

from tests.fakes import composition
from tests.usecases.choice.world import Outside, outside, parts
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.usecases.choice._passport import _passport


def test_an_article_about_another_namesake_does_not_date_the_default_picture(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """🔴 «Мы» (2019) стартовало со строкой «справка знает эту картину как 1989»."""
    rows = [MapPicture("Мы", 2019, False, "Us", 399488)]
    composition.use_known_pictures(monkeypatch, lambda title: rows if title == "Мы" else [])
    world = Outside(passport=Origin(title="Mēs?", year=1989, name="Мы"))

    with outside(world):
        holder = _passport(parts(("Мы", 2019, 47), ("Мы нашли", 2011, 3)))

        assert holder.get() == Origin(title="Us", year=2019, name="Мы", source=SOURCE_MAP)


def test_a_silent_map_leaves_the_article_as_the_passport() -> None:
    """⚠️ Граница: карта о картине молчит - строку года печатают по статье, как печатали."""
    world = Outside(passport=Origin(title="Mēs?", year=1989, name="Мы"))

    with outside(world):
        holder = _passport(parts(("Мы", 2019, 47), ("Мы нашли", 2011, 3)))

        assert holder.get() == Origin(title="Mēs?", year=1989, name="Мы")
