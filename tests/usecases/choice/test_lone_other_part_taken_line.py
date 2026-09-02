"""Зеркало строки взятия единственной чужой части."""

from tests.usecases.choice.world import plan
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.lone_other_part_taken_line import lone_other_part_taken_line


def test_the_taken_part_and_the_menu_door_are_named() -> None:
    ice = [plan("Лёд 3", 2024, part=3, seeders=3)]

    assert lone_other_part_taken_line(ice, "лёд") == phrase(
        "choice.lone_other_part_taken", name="лёд", picture="Лёд 3 (2024)", part=3
    )
