"""Зеркало строки взятия после стража первой части."""

from tests.usecases.choice.world import parts
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.part_one_taken_line import part_one_taken_line


def test_the_guard_the_taken_part_and_the_menu_door_are_named() -> None:
    cars = parts(("Тачки", 2006, 0), ("Тачки 2", 2011, 40))

    assert part_one_taken_line(cars, 2, "тачки", "первая не играет") == phrase(
        "choice.guard_taken",
        guard="первая не играет",
        taken="Тачки 2 (2011)",
        asked="тачки",
    )
