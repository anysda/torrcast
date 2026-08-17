"""Потолок битрейта отбора: на таком ресивер встаёт, и в очередь релиз не идёт."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.over_ceiling import over_ceiling


def test_a_release_above_the_ceiling_does_not_reach_the_queue() -> None:
    assert over_ceiling(rel(size_gb=28), RUNTIME, 20.0), "~28 ГБ на два часа это 33 Мбит/с"
    assert not over_ceiling(rel(size_gb=8), RUNTIME, 20.0)


def test_a_frame_above_1080p_is_judged_by_its_own_ceiling() -> None:
    """У ужатого 4К запас вдвое тоньше, а из роя тянуть надо вес исходника."""
    assert over_ceiling(rel(quality="2160p", size_gb=12), RUNTIME, 20.0, hard_mbit=10.0)
    assert not over_ceiling(rel(quality="1080p", size_gb=12), RUNTIME, 20.0, hard_mbit=10.0)


def test_an_unknown_weight_never_trips_the_ceiling() -> None:
    """🔴 TC-344. Тяжесть такого файла рассудит ffprobe уже после выбора."""
    silent = rel(name="Локи [S01]", kind="tv", size_gb=99)
    assert not over_ceiling(silent, RUNTIME, 20.0)
