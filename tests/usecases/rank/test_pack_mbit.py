"""Потолок битрейта серии у пака, чьё имя считает сезоны, но не серии."""

from __future__ import annotations

import pytest

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.domain.bitrate_mbit import bitrate_mbit
from torrcast.domain.rank_settings import SD_BITRATE
from torrcast.usecases.rank.pack_mbit import pack_mbit


def test_the_ceiling_divides_by_the_smallest_plausible_season() -> None:
    """🟡 «Чёрные паруса»: имя серий не считает, а внутри SD и один сид."""
    pack = rel(
        name="Чёрные паруса [S01-04] HDTV",
        title="Чёрные паруса",
        kind="tv",
        seasons=(1, 2, 3, 4),
        size_gb=10.24,
    )
    assert pack_mbit(pack, RUNTIME) == pytest.approx(bitrate_mbit(pack.size // 24, RUNTIME))
    assert pack_mbit(pack, RUNTIME) < SD_BITRATE, "потолок ниже порога - внутри SD наверняка"


def test_an_honest_big_pack_is_left_alone() -> None:
    big = rel(name="Сериал [S01-04] BDRip 720p", kind="tv", seasons=(1, 2, 3, 4), size_gb=114.0)
    assert pack_mbit(big, RUNTIME) > SD_BITRATE


def test_the_ceiling_is_not_counted_where_it_would_be_a_guess() -> None:
    assert pack_mbit(rel(size_gb=10.24), RUNTIME) == 0.0, "фильм сезонами не делится"
    counted = rel(kind="tv", seasons=(1,), episodes=(1, 2), size_gb=10.24)
    assert pack_mbit(counted, RUNTIME) == 0.0, "счёт серий известен - потолок не нужен"
    assert pack_mbit(rel(kind="tv"), RUNTIME) == 0.0, "сезонов имя не назвало"
