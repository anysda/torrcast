"""HEVC проходит в очередь только последней надеждой и никогда - предпочтением."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.hevc_hope import hevc_hope


def test_hevc_reaches_the_queue_only_when_the_last_hope_is_open() -> None:
    """«Гинтама»: единственный живой носитель первой серии - BDRip-HEVC 720p."""
    hevc = rel(codec="HEVC")
    assert not hevc_hope(hevc, last=False)
    assert hevc_hope(hevc, last=True)


def test_an_ordinary_codec_never_stands_on_this_step() -> None:
    assert not hevc_hope(rel(), last=True)


def test_a_frame_above_1080p_passes_here_too() -> None:
    """🔴 TC-222. Нет 1080p - 2160p перекодируется вниз, а не отбрасывается."""
    assert hevc_hope(rel(codec="HEVC", quality="2160p"), last=True)
