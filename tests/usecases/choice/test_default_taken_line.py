"""Зеркало строки автоматического взятия первой живой картины."""

from tests.usecases.choice.world import parts
from torrcast.domain.catalogs.phrase import phrase
from torrcast.usecases.choice.default_taken_line import default_taken_line


def test_the_taken_picture_the_total_and_the_menu_door_are_named() -> None:
    moana = parts(("Моана: романтика золотого века", 1926, 1), ("Моана", 2016, 222))

    assert default_taken_line(moana, 2, "моана") == phrase(
        "choice.default_taken", picture="Моана (2016)", total=2, asked="моана"
    )
