"""A cold shelf keeps waiting for covers deferred by a 429 and asks them again after the quiet."""

from __future__ import annotations

from pathlib import Path

from hass.hit_posters import FIELD
from hass.shelf_posters import ShelfPosters
from tests.test_hit_claims import _Clock, _posters, _Storm
from tests.test_hit_posters import FakeSource, _row
from tests.test_shelf_posters import _until
from torrcast.domain.json_value import JsonValue


def test_a_cover_deferred_by_a_429_is_still_coming_and_asked_after_the_quiet(
    tmp_path: Path,
) -> None:
    """Rollback (the shelf reads ``arriving`` of the claims): the shelf closes on placeholders."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(calm=119.0)
    covers = ShelfPosters(_posters(tmp_path, source, clock, storm))
    rows: list[JsonValue] = [_row()]

    covers.ask(rows)

    assert covers.arriving(rows), "a cover deferred to the end of the quiet read as not coming"
    assert len(source.judged) == 1, "asked again before the quiet was over"
    clock.now, storm.troubled = 119.0, False
    source.pages = {"Тачки": ["Cars"]}
    covers.arriving(rows)
    assert len(source.judged) == 2, "the quiet is over and nobody asked the cover again"
    _until(lambda: FIELD in covers.landed(rows)[0])  # type: ignore[operator]
    assert FIELD in covers.landed(rows)[0]  # type: ignore[operator]
    assert not covers.arriving(rows)


def test_a_calm_miss_is_not_coming(tmp_path: Path) -> None:
    """No cover in a calm answer: the shelf has nothing to wait for and asks nothing again."""
    source, clock, storm = FakeSource(pages={}), _Clock(), _Storm(troubled=False)
    covers = ShelfPosters(_posters(tmp_path, source, clock, storm))
    rows: list[JsonValue] = [_row()]

    covers.ask(rows)

    assert not covers.arriving(rows)
    assert len(source.judged) == 1
