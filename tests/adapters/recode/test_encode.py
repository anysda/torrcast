"""Модель перекода: потолки, ужатие кадра, тонемап и аргументы видеокодера."""

from __future__ import annotations

import pytest

from tests.adapters.recode.grids import grid
from torrcast.adapters.recode.encode import Encode
from torrcast.adapters.recode.encode_settings import FIT_FLOOR, MAXRATE_GAIN, VBV_SECONDS


def test_the_ceiling_and_the_buffer_are_counted_from_the_target() -> None:
    """Потолок выше цели на 8 %, а буфер VBV считается от потолка, а не от цели."""
    encode = Encode(mbit=9.0)

    assert encode.maxrate == 9.0 * MAXRATE_GAIN
    assert encode.bufsize == encode.maxrate * VBV_SECONDS


def test_the_target_is_counted_from_the_length_of_the_piece() -> None:
    """Один и тот же вес в длинном куске - это меньше Мбит/с, чем в коротком (TC-483)."""
    encode = Encode(mbit=9.0)

    short = encode.fit(span=5.0, cap=16_000_000)
    long = encode.fit(span=20.0, cap=16_000_000)

    assert long.mbit < short.mbit, "длинный кусок обязан просить меньше"
    assert short.mbit <= 9.0, "вверх не перекодируем: потолок умеет только опустить цель"


def test_the_receiver_bitrate_ceiling_lowers_the_target_on_its_own() -> None:
    """Приёмник спотыкается о битрейт независимо от веса куска."""
    encode = Encode(mbit=9.0)

    without = encode.fit(span=2.0, cap=16_000_000)
    with_ceiling = encode.fit(span=2.0, cap=16_000_000, cap_mbit=4.0)

    assert with_ceiling.mbit < without.mbit
    assert encode.fit(span=1000.0, cap=1).mbit == FIT_FLOOR, "ниже пола не опускаемся"


def test_the_frame_is_only_shrunk_when_the_source_is_bigger_than_the_receiver_takes() -> None:
    """Ужимаем габарит, а не высоту, и никогда не растягиваем вверх."""
    big = Encode(frame=2160, ceiling=1080)
    small = Encode(frame=720, ceiling=1080)

    assert big.scaled and big.out_frame == 1080
    assert not small.scaled and small.out_frame == 720
    assert "force_original_aspect_ratio=decrease" in big.filters
    assert "min(iw" in big.filters, "страховка от растягивания мелкого входа"
    assert small.filters == "", "фильтровать нечего - поток идёт как шёл"


def test_the_scale_stands_before_the_tonemap() -> None:
    """Тонемап - самый дорогой фильтр, и цена его линейна по пикселям (TC-223)."""
    chain = Encode(frame=2160, ceiling=1080, hdr=True).filters

    assert chain.index("scale=") < chain.index("tonemap="), "скейл первым, тонемап на 1080p"


def test_the_mark_stays_empty_for_an_untouched_sdr_frame() -> None:
    """Пустая метка оставляет ключи прежних прогонов теми же - прогретое находится."""
    assert Encode(frame=1080, ceiling=1080).mark == ""
    assert Encode(frame=2160, ceiling=1080).mark == ":1080p"
    assert Encode(frame=1080, ceiling=1080, hdr=True).mark == ":sdr"
    assert Encode(frame=2160, ceiling=1080, hdr=True).mark == ":1080p:sdr"


def test_the_forced_key_frames_stand_just_before_the_grid_borders() -> None:
    """``-force_key_frames`` сравнивает время как есть, а граница печатается с тремя знаками.

    Округление вверх уводило опорный кадр на следующий, и на стыке копии с перекодом
    терялся кадр. Поэтому кадры просятся раньше границы на тот же допуск, что и у муксера.
    """
    lines = grid()
    args = Encode(frame=1080, ceiling=1080).args(lines, 0, 1)
    asked = [float(point) for point in args[args.index("-force_key_frames") + 1].split(",")]

    assert asked[0] < lines.start(0), "первый кадр просится РАНЬШЕ начала куска"
    for slot, point in enumerate(asked):
        gap = lines.start(slot) - point
        assert gap == pytest.approx(0.02, abs=5e-4), "ровно допуск муксера, ни больше ни меньше"
    assert "-level" in args and args[args.index("-level") + 1] == "4.1"
    assert "-profile:v" not in args, "потолок профиля не задаётся: он ничего не включает"
