"""Планы круга несут запись ответов каталога самим списком."""

from __future__ import annotations

from tests.usecases.discover.world import row
from torrcast.usecases.discover.told_circle import ToldCircle


def test_the_plans_stay_a_list_and_carry_what_the_catalogue_said() -> None:
    told = [("search", "тачки", 0.0, (), [row("Тачки (2006) 1080p", "a")])]

    circle = ToldCircle([], told)  # type: ignore[arg-type]

    assert (circle, circle.told, ToldCircle().told) == ([], told, [])
