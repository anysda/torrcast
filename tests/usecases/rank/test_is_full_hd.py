"""Имя обещает 1080p и раздача при этом жива."""

from __future__ import annotations

from tests.usecases.rank.releases import rel
from torrcast.usecases.rank.is_full_hd import is_full_hd


def test_a_live_1080p_is_a_step_up_over_720p() -> None:
    """«Мастер и Маргарита»: WEB-DL 720p со 146 сидами стоял выше 1080p с 59."""
    assert is_full_hd(rel(quality="1080p", seeders=30), alive=55)
    assert not is_full_hd(rel(quality="720p", seeders=55), alive=55)


def test_a_share_too_small_is_not_a_step_up() -> None:
    """Поднять такой 1080p значило бы поменять ступень качества на подгрузы."""
    assert not is_full_hd(rel(quality="1080p", seeders=8), alive=100)


def test_the_floor_holds_even_when_the_share_passes() -> None:
    """«Сёгун»: 1080p на трёх сидах против 720p на пяти - доля 0.60, а рой не играет."""
    assert not is_full_hd(rel(quality="1080p", seeders=3), alive=5)


def test_an_interlaced_promise_is_not_full_hd() -> None:
    assert not is_full_hd(rel(quality="1080i", seeders=100), alive=100)


def test_4k_rises_together_with_1080p() -> None:
    assert is_full_hd(rel(quality="2160p", seeders=30), alive=55)
