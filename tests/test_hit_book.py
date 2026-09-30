"""Mirror for :func:`hass.hit_book.hit_book`: who carries a picture's bytes, who writes its miss."""

from __future__ import annotations

from pathlib import Path

from hass.hit_ask import _name
from hass.hit_book import hit_book
from hass.hit_posters import HitPosters
from hass.poster_shelf import PosterShelf
from tests.test_hit_posters import FakeSource
from torrcast.domain.facts.ask import Ask

CARS = Ask("Тачки", 2006, "movie", "Тачки")


def _claims(tmp_path: Path) -> HitPosters:
    return HitPosters(source=FakeSource(), shelf=PosterShelf(home=lambda: tmp_path))


def test_a_picture_already_carried_is_not_handed_to_a_second_fetch(tmp_path: Path) -> None:
    """Rollback (no carried check): the second verdict's answer fetches the bytes again."""
    claims = _claims(tmp_path)
    assert hit_book(claims, [CARS], {CARS: ["Cars"]}, [], [], False, 0.0) == {CARS: ["Cars"]}
    assert hit_book(claims, [CARS], {CARS: ["Cars"]}, [], [], False, 0.0) == {}


def test_an_empty_answer_beside_a_calm_claim_writes_no_miss(tmp_path: Path) -> None:
    """The row's empty race is not the claim owner's verdict: the picture is not put off."""
    claims = _claims(tmp_path)
    assert hit_book(claims, [CARS], {CARS: []}, [], [CARS], False, 0.0) == {}
    assert not claims._tried and not claims._again
    hit_book(claims, [CARS], {CARS: []}, [], [], False, 0.0)
    assert _name(CARS) in claims._tried
