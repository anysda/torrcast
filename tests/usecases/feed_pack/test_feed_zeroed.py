"""Прогретый кусок с затёртым нулями участком зрителю не уходит: место пакуется живьём."""

from __future__ import annotations

from typing import TYPE_CHECKING

import torrcast.usecases.feed_pack.feed_segment as feed_segment
from tests.usecases.feed_pack.world import feed, lay, tract, vault
from tests.usecases.warm.test_zeroed import REAL_HOLE
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.feed_pack.feed_segment import _segment
from torrcast.usecases.warm.segment_start import _Clock

if TYPE_CHECKING:
    from pathlib import Path

    import pytest


def _quiet(slot: int) -> None:
    return None


def test_a_warmed_piece_with_a_zeroed_stretch_is_wiped_and_packed_live(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """«Оно» с закладки: кусок на своём месте сетки, но с нулями внутри картинки."""
    fake = tract()
    said: list[str] = []
    asked: list[int] = []
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store, wait=1.0, log=said.append)
    broken = lay(store.dir, 3)
    broken.write_bytes(REAL_HOLE.read_bytes())
    store.spot(3).touch()
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(30.0, movie=True))

    def pack_live(slot: int) -> bool:
        asked.append(slot)
        lay(show.out, slot)
        return True

    answer = _segment(show, 3, pack_live, _quiet)

    assert answer == show.out / "v3.ts" and asked == [3], "затёртый кусок ушёл зрителю"
    assert not broken.exists(), "затёртый кусок остался ждать следующего показа"
    assert not store.spot(3).exists(), "метка перекода пережила забракованный кусок"
    assert said == [phrase("feed.warm_zeroed", slot=3)]
    assert fake.slept == []


def test_a_clean_warmed_piece_on_its_place_is_still_handed_over(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tract()
    store = vault(tmp_path)
    show = feed(tmp_path, vault=store)
    lay(store.dir, 3)
    monkeypatch.setattr(feed_segment, "segment_start", lambda path: _Clock(30.0, movie=True))

    assert _segment(show, 3, lambda slot: True, _quiet) == store.dir / "v3.ts"
