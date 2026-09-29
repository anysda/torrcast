"""Зеркало контейнера кусков: копия - контейнер приёмника, сплошной перекод - MPEG-TS."""

from __future__ import annotations

from torrcast.domain.android_tv_profile import ANDROID_TV
from torrcast.domain.config import Config
from torrcast.domain.segment_container import FMP4, MPEGTS
from torrcast.usecases.playback.layout import layout
from torrcast.usecases.playback.pack_container import pack_container


def test_a_copy_goes_into_the_receivers_container() -> None:
    """Приставка берёт fMP4 - и прогрев обязан решить так же, иначе греет мимо."""
    assert pack_container(ANDROID_TV, None) == FMP4


def test_a_whole_recode_goes_into_mpegts() -> None:
    """Под сплошным перекодом контейнер один при любом приёмнике."""
    _grid, whole = layout(
        Config(recode=True), "file:///нет-такого", 300.0, "av1", 21.0, depth=8, profile=ANDROID_TV
    )

    assert whole is not None
    assert pack_container(ANDROID_TV, whole) == MPEGTS
