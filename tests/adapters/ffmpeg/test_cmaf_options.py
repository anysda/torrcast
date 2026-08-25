"""Доводы CMAF: каждый кусок несёт свой заголовок, общего у показа нет."""

from __future__ import annotations

from torrcast.adapters.ffmpeg.cmaf_options import CMAF_OPTIONS


def test_every_piece_carries_its_own_head() -> None:
    """У показа два кодировщика и два набора параметров: общий заголовок описал бы один.

    Живой замер: перекод по заголовку копии - 1514 и 1680 строк ошибок картинки на двух
    ужатых местах, со своим заголовком - ноль.
    """
    assert CMAF_OPTIONS[CMAF_OPTIONS.index("-individual_header_trailer") + 1] == "1"
    assert "-segment_header_filename" not in CMAF_OPTIONS, "общего заголовка не пишем"
    assert CMAF_OPTIONS[CMAF_OPTIONS.index("-segment_format_options") + 1] == "movflags=cmaf"
