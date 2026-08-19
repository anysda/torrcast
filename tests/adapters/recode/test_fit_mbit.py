"""Цель перекода под потолки приёмника: вес куска, битрейт приёмника и пол цели."""

from __future__ import annotations

from torrcast.adapters.recode.encode_settings import FIT_FLOOR
from torrcast.adapters.recode.fit_mbit import fit_mbit


def test_the_target_is_counted_from_the_length_of_the_piece() -> None:
    """Один и тот же вес в длинном куске - это меньше Мбит/с, чем в коротком (TC-483)."""
    short = fit_mbit(9.0, span=5.0, cap=16_000_000)
    long = fit_mbit(9.0, span=20.0, cap=16_000_000)

    assert long < short, "длинный кусок обязан просить меньше"
    assert short <= 9.0, "вверх не перекодируем: потолок умеет только опустить цель"


def test_the_receiver_bitrate_ceiling_lowers_the_target_on_its_own() -> None:
    """Приёмник спотыкается о битрейт независимо от веса куска."""
    without = fit_mbit(9.0, span=2.0, cap=16_000_000)
    with_ceiling = fit_mbit(9.0, span=2.0, cap=16_000_000, cap_mbit=4.0)

    assert with_ceiling < without
    assert fit_mbit(9.0, span=1000.0, cap=1) == FIT_FLOOR, "ниже пола не опускаемся"
