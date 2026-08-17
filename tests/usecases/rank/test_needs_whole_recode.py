"""Ступень «играется только сплошным перекодом»: годен, но последним из годных."""

from __future__ import annotations

from tests.usecases.rank.releases import RUNTIME, rel
from torrcast.usecases.rank.needs_whole_recode import needs_whole_recode


def test_a_heavy_release_stands_on_this_step() -> None:
    """Ремукс на 33 Мбит/с обязан уступать честному релизу на 8, даже с большим роем."""
    assert needs_whole_recode(rel(size_gb=28), RUNTIME, hard_mbit=20.0)
    assert not needs_whole_recode(rel(size_gb=8), RUNTIME, hard_mbit=20.0)


def test_a_frame_above_1080p_stands_here_whatever_it_weighs() -> None:
    """🔴 TC-221. 4К играется только сплошным перекодом со скейлом вниз."""
    assert needs_whole_recode(rel(quality="2160p", size_gb=2), RUNTIME, hard_mbit=0.0)


def test_without_recoding_the_step_by_weight_is_gone() -> None:
    """Перекодирование выключено - тяжёлое отсеяно раньше, самим потолком отбора."""
    assert not needs_whole_recode(rel(size_gb=28), RUNTIME, hard_mbit=0.0)
