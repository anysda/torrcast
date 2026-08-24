"""Контейнер сегментов HLS, выбранный профилем приёмника."""

from typing import Final, Literal

MPEGTS: Final = "mpegts"
FMP4: Final = "fmp4"
SegmentContainer = Literal["mpegts", "fmp4"]
