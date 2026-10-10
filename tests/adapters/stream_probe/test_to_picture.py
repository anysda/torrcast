"""Длительность паспорта по концу картинки: сетку двигает только провал, не секунда звука."""

from __future__ import annotations

import math

from torrcast.adapters.stream_probe.to_picture import to_picture
from torrcast.domain.media import Media


def test_only_a_picture_that_ends_well_before_the_container_moves_the_passport() -> None:
    """Обычный звук за кадром (до секунды) едет в последнем куске; сетку двигает лишь провал."""
    media = Media(duration=2702.688)
    assert to_picture(media, 2588.504).duration == 2588.504
    assert to_picture(media, 2701.6).duration == 2702.688, "секунда звука - не провал"
    assert to_picture(media, math.nan).duration == 2702.688
    assert to_picture(Media(duration=0.0), 20.0).duration == 0.0, "неизвестное не выдумываем"
