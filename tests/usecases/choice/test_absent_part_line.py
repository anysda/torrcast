"""Зеркало :mod:`torrcast.usecases.choice.absent_part_line`: строка вместо вопроса.

🔴 TC-830. Решение принято за человека, и строка обязана называть ВЕРНУЮ причину: не
«спрошенное не играет» (оно бы играло, найдись оно), а «спрошенного не нашлось».
"""

from __future__ import annotations

from tests.usecases.choice.world import plan
from torrcast.usecases.choice.absent_part_line import absent_part_line


def test_the_line_names_the_absence_the_taken_picture_and_the_way_to_the_rest() -> None:
    """Три вещи в одной строке: чего не нашлось, что взято и где остальные."""
    cars = [plan("Тачки 2", 2011, part=2, seeders=40), plan("Тачки 3", 2017, part=3, seeders=121)]

    assert absent_part_line(cars, 1, "тачки") == (
        "«тачки»: первой части в выдаче нет; беру первую живую из найденных - "
        "«Тачки 2 (2011)»; всего подошло картин 2; остальные: cast тачки --menu"
    )
