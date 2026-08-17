"""Проверяет предсказание посадки после ``-ss`` по карте: где оно право и где молчит."""

import math

from torrcast.adapters.stream_pack.mapped_start import mapped_start
from torrcast.domain.film_keys import FilmKeys

KEYS = FilmKeys(60.0, [0.0, 2.0, 4.0, 6.0], [0, 1, 2, 3], "mkv")


def test_the_two_demuxers_land_on_different_sides_of_the_same_frame() -> None:
    """mkv берёт строку строго РАНЬШЕ запрошенного, mp4 - не позже, то есть в сам кадр.

    То самое «через один» на «Моане» 2016: ``-ss 66.150`` даёт 62.688.
    """
    assert mapped_start(KEYS, 6.0) == 4.0
    assert mapped_start(KEYS._replace(kind="mp4"), 6.0) == 6.0


def test_the_map_keeps_quiet_where_the_rule_does_not_hold() -> None:
    """``nan`` там, где правила нет: чужой контейнер, край карты, голова файла.

    Голова - не придирка: у начала файла ffmpeg не пускает dts ниже нуля и сдвигает
    метки на кадр-два вперёд (замер: карта обещает 0.000, факт 0.080).
    """
    assert math.isnan(mapped_start(KEYS, 2.0)), "посадка в самое начало файла - не по карте"
    assert math.isnan(mapped_start(KEYS, 0.0)) and math.isnan(mapped_start(KEYS, -1.0))
    assert math.isnan(mapped_start(KEYS, 60.0)), "за краем карты соседней строки нет"
    assert math.isnan(mapped_start(KEYS._replace(kind=""), 6.0)), "контейнер неизвестен"
    assert math.isnan(mapped_start(KEYS._replace(kind="ts"), 6.0)), "у mpegts своё правило"
    assert math.isnan(mapped_start(None, 6.0)), "карты нет - предсказывать нечем"
    assert math.isnan(mapped_start(KEYS._replace(at=[0.0]), 6.0)), "карта в одну строку"
