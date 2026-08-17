"""Сплошной перекод: один пресет на весь фильм и цель по весу исходного видео."""

from __future__ import annotations

from torrcast.adapters.recode.whole_encode import (
    FULL_FLOOR,
    FULL_GAIN,
    FULL_PRESET,
    whole_encode,
)


def test_the_whole_file_goes_by_the_fastest_preset() -> None:
    """Пресет тут не торгуется по сроку: срок один на весь фильм.

    Замер на 4 vCPU: декод HEVC вместе с ``ultrafast`` даёт двукратный запас, а уже
    ``veryfast`` падает до 1.0-1.3x - упаковка идёт вровень с показом.
    """
    assert FULL_PRESET == "ultrafast"
    assert whole_encode(9.0).preset == FULL_PRESET
    assert whole_encode(9.0).mbit == 9.0, "без веса источника берём то, что просили"


def test_light_material_is_not_paid_for_in_bits_it_does_not_have() -> None:
    """Лёгкое аниме в полные 9 Мбит/с - это процессор, потраченный впустую."""
    light = whole_encode(9.0, video_mbit=2.0)

    assert light.mbit == 2.0 * FULL_GAIN, "цена, за которую перекод не видно глазом"
    assert light.mbit < 9.0


def test_the_floor_keeps_the_picture_from_falling_apart() -> None:
    """Ниже этого 1080p на ``ultrafast`` разваливается на блоки, каким бы лёгким ни был вход."""
    assert whole_encode(9.0, video_mbit=0.2).mbit == FULL_FLOOR
    assert FULL_FLOOR == 3.0


def test_the_asked_ceiling_is_never_exceeded() -> None:
    """Вес источника умеет только опустить цель, а поднять её выше просимого - нет."""
    assert whole_encode(4.0, video_mbit=10.0).mbit == 4.0


def test_the_frame_and_the_colour_travel_untouched() -> None:
    """Кадр источника, потолок приёмника и HDR доезжают до модели перекода как есть."""
    encode = whole_encode(9.0, frame=2160, ceiling=1080, hdr=True)

    assert (encode.frame, encode.ceiling, encode.hdr) == (2160, 1080, True)
    assert encode.mark == ":1080p:sdr"
