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


def test_inside_a_gop_both_demuxers_land_on_the_same_row() -> None:
    """Внутри GOP сдвига нет: оба демуксера встают на последний опорный кадр перед местом.

    Замер TC-695 на файле с ровным GOP 7.28 с: ``-ss 110.000`` встаёт на 109.200 и в
    mkv, и в mp4, и в их remux, а прежнее правило обещало 101.920 - промах ровно на один
    опорный кадр, поэтому сверка карты с пробным прогоном на границе внутри GOP не
    сходилась никогда, и файл оставался недоверенным навсегда.
    """
    assert mapped_start(KEYS, 5.0) == 4.0
    assert mapped_start(KEYS._replace(kind="mp4"), 5.0) == 4.0


def test_the_seek_target_is_what_the_command_prints() -> None:
    """Цель захода печатается с тремя знаками (``-ss %.3f``), и округление решает попадание.

    Замер TC-695 на настоящем mp4-релизе: опорный кадр лежит на 373.206167, команда
    печатает ``-ss 373.206`` - НИЖЕ кадра - и ffmpeg встаёт на прежний опорный кадр;
    от 373.207 - ровно на него. Суб-мс метки у релизов - норма, а не экзотика.
    """
    keys = FilmKeys(600.0, [0.0, 100.0, 373.206167, 400.0], [0, 1, 2, 3], "mp4")
    assert mapped_start(keys, 373.206167) == 100.0
    assert mapped_start(keys, 373.207) == 373.206167


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
