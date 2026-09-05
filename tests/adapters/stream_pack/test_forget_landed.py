"""Проверяет снятие числа посадки прошлого показа: новому оно не указ."""

from pathlib import Path

from torrcast.adapters.stream_pack.forget_landed import forget_landed
from torrcast.adapters.stream_pack.landed_path import landed_path
from torrcast.adapters.stream_pack.mark_landed import mark_landed


def test_the_landing_of_the_previous_show_is_taken_away(tmp_path: Path) -> None:
    """Число прошлого показа местом посадки нового не является - и остаться не должно."""
    mark_landed(tmp_path, 2450.0)
    forget_landed(tmp_path)
    assert not landed_path(tmp_path).exists()


def test_there_is_nothing_to_take_away_and_that_is_fine(tmp_path: Path) -> None:
    """Числа не было - не беда: снимать нечего, а падать тут нельзя."""
    forget_landed(tmp_path)
    forget_landed(tmp_path / "нет-такого")
