"""Паспорт перед добором сверяется с выдачей: :func:`_second_origin` с ``found``."""

from __future__ import annotations

from typing import Any

import pytest

from tests.fakes import composition
from torrcast.domain.facts.map_picture import MapPicture
from torrcast.domain.facts.origin import Origin
from torrcast.domain.facts.settings import SOURCE_MAP
from torrcast.domain.picture import Picture
from torrcast.usecases.discover._second_origin import _second_origin

_MES = Origin(title="Mēs?", year=1989, name="Мы")


def _article(name: str, **kwargs: Any) -> Origin:
    return _MES


@pytest.fixture
def us_in_the_map(monkeypatch: pytest.MonkeyPatch) -> None:
    rows = [MapPicture("Мы", 2019, False, "Us", 399488)]
    composition.use_known_pictures(monkeypatch, lambda title: rows if title == "Мы" else [])


@pytest.mark.usefixtures("us_in_the_map")
def test_an_article_about_another_namesake_yields_to_the_picture_of_the_pool() -> None:
    """🔴 «Мы»: второй круг уходил за «Мы 1989», гейт его отвергал, и выходило «ничего»."""
    about = _second_origin(_article, "Мы", None, None, 1.5, [Picture(title="Мы", year=2019)])

    assert about == Origin(title="Us", year=2019, name="Мы", source=SOURCE_MAP)


@pytest.mark.usefixtures("us_in_the_map")
def test_without_the_pool_the_article_is_returned_as_it_came() -> None:
    assert _second_origin(_article, "Мы", None, None, 1.5) == _MES


@pytest.mark.usefixtures("us_in_the_map")
def test_a_numbered_part_still_drops_the_year_whatever_the_pool() -> None:
    about = _second_origin(_article, "Мы", None, 2, 1.5, [Picture(title="Мы", year=2019)])

    assert about.year is None
