"""Зеркало правила: держал ли рой сеанс - по окну наблюдений, а не по последнему замеру."""

from __future__ import annotations

from torrcast.domain.swarm_kept_up import swarm_kept_up


def test_one_healthy_reading_of_the_session_clears_the_swarm() -> None:
    """Доли из следа замера 03-09-2026: рой вёз втрое сверх нужного, последний замер снят
    уже после того, как показ сдался тянуть, - и рой им не судят."""
    assert swarm_kept_up([3.61, 2.99, 3.20, 3.44, 0.01])


def test_a_swarm_that_never_kept_up_stays_to_blame() -> None:
    """Ни одного здорового наблюдения за сеанс - приговор рою остаётся, и он верен."""
    assert not swarm_kept_up([0.02, 0.01, 0.01, 0.01])
    assert not swarm_kept_up([]), "наблюдений нет - хвалить рой не за что"


def test_the_boundary_is_one_source_second_per_wall_second() -> None:
    """Ровно 1.0x - это «успевает»: секунда исходника за секунду стены."""
    assert swarm_kept_up([0.99, 1.0])
    assert not swarm_kept_up([0.99, 0.999])
