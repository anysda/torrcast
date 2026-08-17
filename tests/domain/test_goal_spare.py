"""Проверяет остаток продуктовой цели и доли, которые от неё отмеряются."""

from torrcast.domain.goal_spare import CIRCLE_SHARE, GOAL, SECOND_LEAST, goal_spare


def test_остаток_цели_считается_от_потраченного() -> None:
    assert goal_spare(0.0) == GOAL
    assert goal_spare(4.0) == GOAL - 4.0


def test_съеденная_цель_даёт_ноль_а_не_долг() -> None:
    """Отрицательным бюджетом спрашивать нечего: круг с ним не заводят."""
    assert goal_spare(GOAL) == 0.0
    assert goal_spare(GOAL * 3) == 0.0


def test_доли_цели_меньше_её_самой_и_растут_по_смыслу() -> None:
    """Круг дешевле секунды не бывает, а второй заход без справки и круга не живёт."""
    assert 0 < CIRCLE_SHARE < SECOND_LEAST < GOAL
